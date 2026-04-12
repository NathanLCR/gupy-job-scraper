from datetime import datetime, UTC

from sqlalchemy import select

from database import SessionLocal
from entities.search_term import SearchTerm


def get_search_terms(include_inactive: bool = True):
    db = SessionLocal()
    stm = select(SearchTerm)
    if not include_inactive:
        stm = stm.where(SearchTerm.is_active)
    terms = db.scalars(stm).all()
    db.close()
    return terms


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