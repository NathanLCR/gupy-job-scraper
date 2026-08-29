"""Resumable bounded PostgreSQL search-document backfill."""

import argparse
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import SessionLocal
from entities import Job

logger = logging.getLogger("skillpulse.search_document_backfill")


@dataclass(frozen=True)
class BackfillResult:
    scanned: int
    updated: int
    last_id: int


def backfill_search_documents(
    db: Session,
    *,
    batch_size: int = 500,
    start_after_id: int = 0,
    max_batches: Optional[int] = None,
) -> BackfillResult:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        raise RuntimeError("Search-document backfill requires PostgreSQL")
    batch_size = min(500, max(1, int(batch_size)))
    cursor = max(0, int(start_after_id))
    scanned = updated = batches = 0

    while max_batches is None or batches < max_batches:
        ids = list(
            db.scalars(
                select(Job.id)
                .where(Job.id > cursor, Job.search_document.is_(None))
                .order_by(Job.id.asc())
                .limit(batch_size)
            ).all()
        )
        if not ids:
            break
        for job_id in ids:
            db.execute(
                text("SELECT refresh_job_search_document(:job_id)"),
                {"job_id": int(job_id)},
            )
            cursor = int(job_id)
        db.commit()
        scanned += len(ids)
        updated += len(ids)
        batches += 1
        logger.info(
            "search_document_backfill_batch_completed",
            extra={
                "event": "search_document_backfill_batch_completed",
                "updated": len(ids),
                "last_id": cursor,
            },
        )
    return BackfillResult(scanned=scanned, updated=updated, last_id=cursor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--start-after-id", type=int, default=0)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = backfill_search_documents(
            db,
            batch_size=args.batch_size,
            start_after_id=args.start_after_id,
            max_batches=args.max_batches,
        )
    print(f"updated={result.updated} last_id={result.last_id}")


if __name__ == "__main__":
    main()
