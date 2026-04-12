import json
from typing import Any
from sqlalchemy import desc, func, or_, select

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

def _build_pagination(total_items: int, page: int, page_size: int) -> dict:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    return {
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def get_errors(
    *,
    search: str | None = None,
    source: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    paginated: bool = False,
):
    db = SessionLocal()
    try:
        query = select(ErrorLog)

        if source:
            query = query.where(ErrorLog.source == source)

        if search:
            search_value = f"%{search.strip()}%"
            query = query.where(
                or_(
                    ErrorLog.message.ilike(search_value),
                    ErrorLog.source.ilike(search_value),
                    ErrorLog.term.ilike(search_value),
                )
            )

        query = query.order_by(desc(ErrorLog.created_at), desc(ErrorLog.id))

        if not paginated:
            errors = db.scalars(query).all()
            return [error.to_dict() for error in errors]

        safe_page = max(1, page or 1)
        safe_page_size = max(1, min(page_size or 20, 100))
        total_items = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = db.scalars(
            query.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
        ).all()
        return {
            "items": [error.to_dict() for error in items],
            "pagination": _build_pagination(total_items, safe_page, safe_page_size),
        }
    finally:
        db.close()
