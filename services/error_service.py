import json
from typing import Any
from sqlalchemy import select, desc

from database import SessionLocal
from entities import ErrorLog


def log_error(
    message: str,
    term: str | None = None,
    page: int | None = None,
    request_limit: int | None = None,
    payload: Any = None,
    *,
    source: str):
    db = SessionLocal()
    try:
        db.add(
            ErrorLog(
                source=source,
                message=message,
                term=term,
                page=page,
                request_limit=request_limit,
                payload=(json.dumps(payload, ensure_ascii=False) if payload is not None else None)
            )
        )
        db.commit()
    except Exception as exc: 
        db.rollback()
        print(f"[log_error failed] {exc}: {message}")
    finally:
        db.close()

def get_errors():
    db = SessionLocal()
    try:
        errors = db.scalars(select(ErrorLog).order_by(desc(ErrorLog.created_at))).all()
        return [error.to_dict() for error in errors]
    finally:
        db.close()