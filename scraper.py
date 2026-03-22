import json
from datetime import UTC, date, datetime
from random import randint
from time import sleep
from typing import Any

import requests
from sqlalchemy import select

from database import SessionLocal, init_db
from entities import ErrorLog, JobsPost, SearchTerm

BASE_URL = "https://employability-portal.gupy.io/api/v1/jobs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
}


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def log_error(
    db,
    message: str,
    term: str | None = None,
    page: int | None = None,
    request_limit: int | None = None,
    payload: Any = None,
) -> None:
    entry = ErrorLog(
        source="fetch_gupy_jobs_post",
        message=message,
        term=term,
        page=page,
        request_limit=request_limit,
        payload=json.dumps(payload, ensure_ascii=False)
        if payload is not None
        else None,
    )
    db.add(entry)
    db.commit()


def fetch_gupy_jobs_post(db, term: str, page: int, limit: int) -> dict[str, Any] | None:
    params = {"jobName": term, "limit": limit, "offset": str((page * limit) - limit)}
    try:
        response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        log_error(db, f"HTTP error: {exc}", term, page, limit, params)
        return None
    except ValueError:
        log_error(db, "Invalid JSON returned by Gupy API", term, page, limit, params)
        return None

    if "data" not in payload or not isinstance(payload.get("data"), list):
        log_error(
            db, "Malformed API payload: missing data list", term, page, limit, payload
        )
        return None

    return payload


def get_active_search_terms(db) -> list[str]:
    return db.scalars(
        select(SearchTerm.term).where(SearchTerm.is_active.is_(True))
    ).all()


def save_job_post(db, row: dict[str, Any]) -> bool:
    row_id = row.get("id")
    if row_id is None:
        return False

    db.add(
        JobsPost(
            id=row_id,
            company_id=row.get("companyId"),
            name=row.get("name", ""),
            description=row.get("description"),
            career_page_id=row.get("careerPageId"),
            career_page_name=row.get("careerPageName"),
            career_page_logo=row.get("careerPageLogo"),
            career_page_url=row.get("careerPageUrl"),
            job_type=row.get("type"),
            published_date=parse_datetime(row.get("publishedDate")),
            application_deadline=parse_date(row.get("applicationDeadline")),
            is_remote_work=row.get("isRemoteWork"),
            city=row.get("city"),
            state=row.get("state"),
            country=row.get("country"),
            job_url=row.get("jobUrl"),
            workplace_type=row.get("workplaceType"),
            disabilities=row.get("disabilities"),
            skills=json.dumps(row.get("skills"), ensure_ascii=False),
            badges=json.dumps(row.get("badges"), ensure_ascii=False),
        )
    )
    return True


def populate_database(limit: int = 20) -> int:
    init_db()
    db = SessionLocal()
    inserted = 0

    try:
        existing_ids = set(db.scalars(select(JobsPost.id)).all())
        search_terms = get_active_search_terms(db)

        for term in search_terms:
            page = 1
            while True:
                response = fetch_gupy_jobs_post(db, term, page, limit)
                if response is None:
                    break

                rows = response.get("data", [])
                if not rows:
                    break

                for row in rows:
                    row_id = row.get("id")
                    if row_id is None:
                        log_error(
                            db, "Job without id in payload", term, page, limit, row
                        )
                        continue
                    if row_id in existing_ids:
                        continue
                    if save_job_post(db, row):
                        existing_ids.add(row_id)
                        inserted += 1

                db.commit()
                page += 1
                sleep(randint(2, 5))
    finally:
        db.close()

    print(f"Initial population inserted {inserted} jobs.")
    return inserted


def scrape() -> None:
    init_db()
    db = SessionLocal()
    inserted = 0

    try:
        existing_ids = set(db.scalars(select(JobsPost.id)).all())
        search_terms = get_active_search_terms(db)

        for term in search_terms:
            page = 1
            limit = 20

            while True:
                response = fetch_gupy_jobs_post(db, term, page, limit)
                if response is None:
                    break

                rows = response.get("data", [])
                if not rows:
                    break

                page_has_only_old_rows = True
                for row in rows:
                    row_id = row.get("id")
                    if row_id is None:
                        log_error(
                            db, "Job without id in payload", term, page, limit, row
                        )
                        continue

                    published_dt = parse_datetime(row.get("publishedDate"))
                    if row_id in existing_ids:
                        continue

                    if save_job_post(db, row):
                        existing_ids.add(row_id)
                        inserted += 1
                        page_has_only_old_rows = False

                db.commit()

                if page_has_only_old_rows:
                    break

                page += 1
                sleep(randint(2, 5))
    finally:
        db.close()

    print(f"Inserted {inserted} new jobs.")


if __name__ == "__main__":
    populate_database()
