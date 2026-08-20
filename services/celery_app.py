from celery import Celery
from config import settings

celery_app = Celery(
    "skillpulse_ai",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max for big scraping batches
)


@celery_app.task(name="tasks.scrape_jobs")
def task_scrape_jobs(term: str = None, limit: int = 20):
    """Celery background task for scraping job postings."""
    from services.scraper_service_hm import start_scrape_thread
    start_scrape_thread()
    return {"status": "started", "term": term, "limit": limit}


@celery_app.task(name="tasks.batch_extract")
def task_batch_extract(engine: str = "regex", limit: int = None):
    """Celery background task for batch feature extraction."""
    from services.extractor_service import start_extractor_thread, start_llm_extractor_thread
    if engine == "llm":
        start_llm_extractor_thread(limit=limit)
    else:
        start_extractor_thread("regex", limit=limit)
    return {"status": "started", "engine": engine, "limit": limit}
