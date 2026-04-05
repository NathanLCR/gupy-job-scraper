import json
from typing import Any
from sqlalchemy import select, desc

from database import SessionLocal
from entities import ErrorLog
from utils import _serialize_error


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

def get_errors(limit: int = 50):
    db = SessionLocal()
    try:
        rows = db.scalars(select(ErrorLog).order_by(desc(ErrorLog.created_at)).limit(limit)).all()
        return [_serialize_error(row) for row in rows]
    finally:
        db.close()