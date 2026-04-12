from datetime import datetime, UTC

from sqlalchemy import func, select

from database import SessionLocal
from entities.search_term import SearchTerm


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


def get_search_terms(
    *,
    include_inactive: bool = False,
    search: str | None = None,
    status: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    paginated: bool = False,
):
    db = SessionLocal()
    try:
        stm = select(SearchTerm)

        if not include_inactive and status != "inactive":
            stm = stm.where(SearchTerm.is_active.is_(True))

        if status == "active":
            stm = stm.where(SearchTerm.is_active.is_(True))
        elif status == "inactive":
            stm = stm.where(SearchTerm.is_active.is_(False))

        if search:
            stm = stm.where(SearchTerm.term.ilike(f"%{search.strip()}%"))

        stm = stm.order_by(SearchTerm.id.desc())

        if not paginated:
            return db.scalars(stm).all()

        safe_page = max(1, page or 1)
        safe_page_size = max(1, min(page_size or 20, 100))
        total_items = db.scalar(select(func.count()).select_from(stm.subquery())) or 0
        items = db.scalars(
            stm.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
        ).all()

        return {
            "items": [term.to_dict() for term in items],
            "pagination": _build_pagination(total_items, safe_page, safe_page_size),
        }
    finally:
        db.close()


def add_search_term(term):
    db = SessionLocal()
    new_term = SearchTerm(term=term)
    db.add(new_term)
    db.commit()
    db.refresh(new_term)
    db.close()
    return new_term


def update_search_term(id, *, is_active: bool):
    db = SessionLocal()
    term_obj = db.get(SearchTerm, id)
    if term_obj is None:
        db.close()
        raise ValueError("Search term not found")
    term_obj.is_active = is_active
    db.commit()
    db.refresh(term_obj)
    db.close()
    return term_obj


def remove_search_term(id):
    db = SessionLocal()
    term_obj = db.get(SearchTerm, id)
    if term_obj is None:
        db.close()
        raise ValueError("Search term not found")
    db.delete(term_obj)
    db.commit()
    db.close()


def update_last_scraped_at(id):
    db = SessionLocal()
    term_obj = db.get(SearchTerm, id)
    if term_obj:
        term_obj.last_scraped_at = datetime.now(UTC)
        db.commit()
    db.close()
