from flask import request
from datetime import datetime, date, UTC

from entities import ErrorLog, JobPost, SearchTerm, Job


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def _get_pagination_limit(default: int = 100, max_value: int = 500) -> int:
    value = request.args.get("limit", default=default, type=int)
    if value is None:
        return default
    return max(1, min(value, max_value))


def _get_pagination_offset(default: int = 0) -> int:
    value = request.args.get("offset", default=default, type=int)
    if value is None:
        return default
    return max(0, value)


def _serialize_job_post(row: JobPost) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "name": row.name,
        "description": row.description,
        "career_page_id": row.career_page_id,
        "career_page_name": row.career_page_name,
        "career_page_logo": row.career_page_logo,
        "career_page_url": row.career_page_url,
        "job_type": row.job_type,
        "published_date": row.published_date.isoformat() if row.published_date else None,
        "application_deadline": row.application_deadline.isoformat() if row.application_deadline else None,
        "is_remote_work": row.is_remote_work,
        "city": row.city,
        "state": row.state,
        "country": row.country,
        "job_url": row.job_url,
        "workplace_type": row.workplace_type,
        "disabilities": row.disabilities,
        "skills": row.skills,
        "badges": row.badges,
    }


def _serialize_error(row: ErrorLog) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "message": row.message,
        "term": row.term,
        "page": row.page,
        "request_limit": row.request_limit,
        "payload": row.payload,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_search_term(row: SearchTerm) -> dict:
    return {"id": row.id, "term": row.term, "is_active": row.is_active}


def _job_post_to_csv_row(row: JobPost) -> list:
    return [
        row.id,
        row.company_id,
        row.name,
        row.description or "",
        row.career_page_id,
        row.career_page_name or "",
        row.career_page_logo or "",
        row.career_page_url or "",
        row.job_type or "",
        row.published_date.isoformat() if row.published_date else "",
        row.application_deadline.isoformat() if row.application_deadline else "",
        row.is_remote_work if row.is_remote_work is not None else "",
        row.city or "",
        row.state or "",
        row.country or "",
        row.job_url or "",
        row.workplace_type or "",
        row.disabilities if row.disabilities is not None else "",
        row.skills or "",
        row.badges or "",
    ]


JOB_POSTS_CSV_HEADERS = [
    "id",
    "company_id",
    "name",
    "description",
    "career_page_id",
    "career_page_name",
    "career_page_logo",
    "career_page_url",
    "job_type",
    "published_date",
    "application_deadline",
    "is_remote_work",
    "city",
    "state",
    "country",
    "job_url",
    "workplace_type",
    "disabilities",
    "skills",
    "badges",
]

def _serialize_job(row: Job) -> dict:
    return {
        "id": row.id,
        "job_title": row.job_title,
        "salary": row.salary,
        "tech_stack": row.tech_stack,
        "company": row.company.name if row.company else None,
        "contract_type": row.contract_type.name if getattr(row, "contract_type", None) else None,
        "state": row.state.name if getattr(row, "state", None) else None,
        "city": row.city.name if getattr(row, "city", None) else None,
        "hard_skills": [skill.name for skill in row.hard_skills] if getattr(row, "hard_skills", None) else [],
        "soft_skills": [skill.name for skill in row.soft_skills] if getattr(row, "soft_skills", None) else [],
        "nice_to_have_skills": [skill.name for skill in row.nice_to_have_skills] if getattr(row, "nice_to_have_skills", None) else [],
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