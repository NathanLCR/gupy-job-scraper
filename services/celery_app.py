from celery import Celery
from config import settings

celery_app = Celery(
    "skillpulse_ai",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL or "redis://localhost:6379/0",
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL or "redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max for big scraping batches
    beat_schedule={
        "bounded-job-reembedding": {
            "task": "tasks.backfill_job_embeddings",
            "schedule": settings.EMBEDDING_REEMBED_INTERVAL_SECONDS,
            "kwargs": {"batch_size": 100, "max_batches": 1},
        }
    },
)


@celery_app.task(name="tasks.scrape_jobs")
def task_scrape_jobs(term: str = None, limit: int = 20, source: str = "all"):
    """Celery background task for scraping job postings synchronously within worker."""
    from services.ingestion.ingestion_manager import ingestion_manager
    terms = [term] if term else None
    result = ingestion_manager.ingest(source=source, terms=terms, limit_per_source=limit, auto_extract=True)
    return result


@celery_app.task(name="tasks.batch_extract")
def task_batch_extract(engine: str = "cascade", limit: int = None):
    """Celery background task for batch feature extraction synchronously within worker."""
    from services.extractor_service import (
        _run_extractor,
        extract_cascade,
        regex_extract,
        bert_extract,
        llm_extract,
    )
    extractor_map = {
        "regex": (regex_extract, "regex_extractor"),
        "bert": (bert_extract, "bert_extractor"),
        "llm": (llm_extract, "llm_extractor"),
        "cascade": (extract_cascade, "cascade_extractor"),
    }
    fn, err_src = extractor_map.get(engine, (extract_cascade, "cascade_extractor"))
    _run_extractor(engine, fn, error_source=err_src, limit=limit)
    return {"status": "completed", "engine": engine, "limit": limit}


@celery_app.task(name="tasks.backfill_job_embeddings")
def task_backfill_job_embeddings(batch_size: int = 100, max_batches: int = 1):
    from database import SessionLocal
    from scripts.backfill_job_embeddings import backfill_job_embeddings

    with SessionLocal() as db:
        result = backfill_job_embeddings(
            db, batch_size=batch_size, max_batches=max_batches
        )
    return {
        "scanned": result.scanned,
        "updated": result.updated,
        "last_id": result.last_id,
    }


@celery_app.task(name="tasks.backfill_search_documents")
def task_backfill_search_documents(batch_size: int = 500, max_batches: int = 1):
    from database import SessionLocal
    from scripts.backfill_search_documents import backfill_search_documents

    with SessionLocal() as db:
        result = backfill_search_documents(
            db, batch_size=batch_size, max_batches=max_batches
        )
    return {
        "scanned": result.scanned,
        "updated": result.updated,
        "last_id": result.last_id,
    }
