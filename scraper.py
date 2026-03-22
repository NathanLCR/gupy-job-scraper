"""
Gupy job scraper: fetch jobs per active search terms, persist to JobsPost, log errors to ErrorLog.

Error logs always use a separate DB session so logging never commits pending job rows.

Incremental mode: for each term, paginate until a full page adds no new job IDs (all rows were
already in DB). Assumes API returns roughly newest-first. Stops on empty page. With an empty
jobs table, keeps paging until the API returns no rows (same as populate for that term).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from random import randint
from time import sleep
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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

DEFAULT_SEARCH_TERMS = [
    "Desenvolvedor",
    "Engenheiro de software",
    "Developer",
    "software engineer",
    "data science",
    "Cientista de dados",
    "Tech lead",
]

FETCH_MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


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
    message: str,
    term: str | None = None,
    page: int | None = None,
    request_limit: int | None = None,
    payload: Any = None,
    *,
    source: str = "fetch_gupy_jobs_post",
) -> None:
    log_db = SessionLocal()
    try:
        log_db.add(
            ErrorLog(
                source=source,
                message=message,
                term=term,
                page=page,
                request_limit=request_limit,
                payload=json.dumps(payload, ensure_ascii=False)
                if payload is not None
                else None,
            )
        )
        log_db.commit()
    except Exception as exc:  # noqa: BLE001
        log_db.rollback()
        print(f"[log_error failed] {exc}: {message}")
    finally:
        log_db.close()


def get_active_search_terms(db) -> list[str]:
    terms = db.scalars(
        select(SearchTerm.term)
        .where(SearchTerm.is_active.is_(True))
        .order_by(SearchTerm.id.asc())
    ).all()
    if terms:
        return list(terms)
    log_error(
        "No active search terms in DB; using DEFAULT_SEARCH_TERMS fallback.",
        source="scraper",
        payload={"default_terms": DEFAULT_SEARCH_TERMS},
    )
    return list(DEFAULT_SEARCH_TERMS)


def fetch_gupy_jobs_post(term: str, page: int, limit: int) -> dict[str, Any] | None:
    params = {"jobName": term, "limit": limit, "offset": str((page * limit) - limit)}

    for attempt in range(1, FETCH_MAX_RETRIES + 1):
        try:
            response = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=30,
            )
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < FETCH_MAX_RETRIES:
                sleep(2**attempt)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                log_error(
                    f"HTTP {response.status_code}: {exc}",
                    term,
                    page,
                    limit,
                    {
                        "params": params,
                        "status_code": response.status_code,
                        "body_preview": (response.text or "")[:800],
                        "attempt": attempt,
                    },
                )
                return None

            try:
                payload = response.json()
            except ValueError:
                log_error(
                    "Invalid JSON returned by Gupy API",
                    term,
                    page,
                    limit,
                    {
                        "params": params,
                        "status_code": response.status_code,
                        "body_preview": (response.text or "")[:800],
                    },
                )
                return None

            if "data" not in payload or not isinstance(payload.get("data"), list):
                log_error(
                    "Malformed API payload: missing or invalid 'data' list",
                    term,
                    page,
                    limit,
                    {
                        "params": params,
                        "keys": list(payload.keys()) if isinstance(payload, dict) else None,
                    },
                )
                return None

            return payload

        except requests.RequestException as exc:
            if attempt < FETCH_MAX_RETRIES:
                sleep(2**attempt)
                continue
            log_error(
                f"Request failed after {FETCH_MAX_RETRIES} attempts: {exc}",
                term,
                page,
                limit,
                {"params": params, "attempt": attempt, "error": str(exc)},
            )
            return None

    return None


def _build_jobs_post(row: dict[str, Any]) -> JobsPost:
    return JobsPost(
        id=row["id"],
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


def insert_job_post(
    db,
    row: dict[str, Any],
    *,
    term: str,
    page: int,
    existing_ids: set[Any],
) -> bool:
    row_id = row.get("id")
    if row_id is None:
        log_error("Job without id in payload", term, page, None, row, source="scraper")
        return False
    try:
        with db.begin_nested():
            db.add(_build_jobs_post(row))
            db.flush()
        return True
    except IntegrityError:
        existing_ids.add(row_id)
        return False


def populate_database(limit: int = 20) -> int:
    init_db()
    db = SessionLocal()
    inserted = 0

    try:
        existing_ids = set(db.scalars(select(JobsPost.id)).all())
        search_terms = get_active_search_terms(db)

        if not search_terms:
            log_error("No search terms available (DB empty and no defaults).", source="scraper")
            return 0

        for term in search_terms:
            page = 1
            while True:
                response = fetch_gupy_jobs_post(term, page, limit)
                if response is None:
                    log_error(
                        f"Stopping term '{term}' after fetch failure at page {page}.",
                        term,
                        page,
                        limit,
                        source="scraper",
                    )
                    break

                rows = response.get("data", [])
                if not rows:
                    break

                for row in rows:
                    row_id = row.get("id")
                    if row_id is None:
                        continue
                    if row_id in existing_ids:
                        continue
                    if insert_job_post(db, row, term=term, page=page, existing_ids=existing_ids):
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

        if not search_terms:
            log_error("No search terms available (DB empty and no defaults).", source="scraper")
            return

        for term in search_terms:
            page = 1
            page_limit = 20

            while True:
                response = fetch_gupy_jobs_post(term, page, page_limit)
                if response is None:
                    log_error(
                        f"Stopping incremental scrape for term '{term}' after fetch failure at page {page}.",
                        term,
                        page,
                        page_limit,
                        source="scraper",
                    )
                    break

                rows = response.get("data", [])
                if not rows:
                    break

                page_inserted = 0
                for row in rows:
                    row_id = row.get("id")
                    if row_id is None:
                        continue
                    if row_id in existing_ids:
                        continue
                    if insert_job_post(db, row, term=term, page=page, existing_ids=existing_ids):
                        existing_ids.add(row_id)
                        inserted += 1
                        page_inserted += 1

                db.commit()

                if page_inserted == 0:
                    break

                page += 1
                sleep(randint(2, 5))
    finally:
        db.close()

    print(f"Inserted {inserted} new jobs.")
