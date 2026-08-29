from sqlalchemy import delete

from config import settings
from database import SessionLocal
from entities import Company, Job
from services.embedding_service import EmbeddingResult


def test_embedding_backfill_is_bounded_and_idempotent(monkeypatch):
    from scripts import backfill_job_embeddings as backfill

    region = "Embedding Backfill Test Region"
    db = SessionLocal()
    calls = []
    try:
        company = db.query(Company).first()
        current = Job(
            job_title="Current",
            extractor_type="regex",
            company_id=company.id,
            region=region,
            embedding=[0.1] * 384,
            embedding_model=settings.ACTIVE_EMBEDDING_MODEL,
        )
        stale = Job(
            job_title="Stale",
            extractor_type="regex",
            company_id=company.id,
            region=region,
            embedding=[0.2] * 384,
            embedding_model="old-model",
        )
        missing = Job(
            job_title="Missing",
            extractor_type="regex",
            company_id=company.id,
            region=region,
        )
        db.add_all([current, stale, missing])
        db.commit()

        def fake_batch(texts):
            calls.append(list(texts))
            return [
                EmbeddingResult([0.3] * 384, settings.ACTIVE_EMBEDDING_MODEL)
                for _ in texts
            ]

        monkeypatch.setattr(backfill, "embed_batch_checked", fake_batch)
        first = backfill.backfill_job_embeddings(db, batch_size=2)
        second = backfill.backfill_job_embeddings(db, batch_size=2)

        db.refresh(current)
        db.refresh(stale)
        db.refresh(missing)
        assert first.updated >= 2
        assert second.updated == 0
        assert current.embedding == [0.1] * 384
        assert stale.embedding_model == settings.ACTIVE_EMBEDDING_MODEL
        assert missing.embedding_model == settings.ACTIVE_EMBEDDING_MODEL
        assert all(len(batch) <= 2 for batch in calls)
    finally:
        db.execute(delete(Job).where(Job.region == region))
        db.commit()
        db.close()


def test_celery_beat_registers_bounded_reembedding_task():
    from services.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["bounded-job-reembedding"]
    assert entry["task"] == "tasks.backfill_job_embeddings"
    assert entry["schedule"] == settings.EMBEDDING_REEMBED_INTERVAL_SECONDS
    assert entry["kwargs"]["batch_size"] <= 100
