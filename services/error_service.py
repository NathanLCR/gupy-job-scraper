import json
from typing import Any

from database import SessionLocal
from entities import ErrorLog


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
    except Exception as exc: 
        log_db.rollback()
        print(f"[log_error failed] {exc}: {message}")
    finally:
        log_db.close()