from datetime import date, datetime, UTC
from typing import Optional

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
    "region",
    "country_code",
    "currency",
    "fingerprint",
]


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None