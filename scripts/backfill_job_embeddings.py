"""Resumable bounded job-embedding backfill."""

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from entities import Job
from services.embedding_service import _format_job_text, embed_batch_checked

logger = logging.getLogger("skillpulse.embedding_backfill")


@dataclass(frozen=True)
class BackfillResult:
    scanned: int
    updated: int
    last_id: int


def backfill_job_embeddings(
    db: Session,
    *,
    batch_size: int = 100,
    start_after_id: int = 0,
    max_batches: Optional[int] = None,
) -> BackfillResult:
    batch_size = min(100, max(1, int(batch_size)))
    cursor = max(0, int(start_after_id))
    scanned = updated = batches = 0

    while max_batches is None or batches < max_batches:
        jobs = db.scalars(
            select(Job)
            .where(
                Job.id > cursor,
                or_(
                    Job.embedding.is_(None),
                    Job.embedding_model.is_(None),
                    Job.embedding_model != settings.ACTIVE_EMBEDDING_MODEL,
                ),
            )
            .order_by(Job.id.asc())
            .limit(batch_size)
        ).unique().all()
        if not jobs:
            break

        texts = [
            _format_job_text(
                job.job_title,
                job.tech_stack or [],
                [skill.name for skill in (job.hard_skills or [])],
                job.description,
                job.seniority,
            )
            for job in jobs
        ]
        results = embed_batch_checked(texts)
        if len(results) != len(jobs):
            db.rollback()
            raise RuntimeError("Embedding provider returned an incomplete batch")

        updated_at = datetime.now(UTC)
        for job, result in zip(jobs, results):
            if len(result.vector) != settings.EMBEDDING_DIM:
                db.rollback()
                raise RuntimeError("Embedding provider returned an invalid dimension")
            job.embedding = result.vector
            job.embedding_model = result.model
            job.embedding_updated_at = updated_at
            cursor = int(job.id)
            updated += 1
        scanned += len(jobs)
        db.commit()
        batches += 1
        logger.info(
            "embedding_backfill_batch_completed",
            extra={
                "event": "embedding_backfill_batch_completed",
                "updated": len(jobs),
                "last_id": cursor,
            },
        )

    return BackfillResult(scanned=scanned, updated=updated, last_id=cursor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--start-after-id", type=int, default=0)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = backfill_job_embeddings(
            db,
            batch_size=args.batch_size,
            start_after_id=args.start_after_id,
            max_batches=args.max_batches,
        )
    print(f"updated={result.updated} last_id={result.last_id}")


if __name__ == "__main__":
    main()
