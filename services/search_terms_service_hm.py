from sqlalchemy import select, insert, update
from database import SessionLocal
from entities.search_term import SearchTerm
from datetime import datetime, UTC

def get_search_terms():
    db = SessionLocal()
    stm = select(SearchTerm)
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

def remove_search_term(id):
    db = SessionLocal()
    term_obj = db.query(SearchTerm).filter_by(id=id).first()
    if term_obj is None:
        db.close()
        raise ValueError("Search term not found")
    term_obj.is_active = False
    db.commit()
    db.refresh(term_obj)
    db.close()
    return term_obj

def update_last_scraped_at(id):
    db = SessionLocal()
    term_obj = db.get(SearchTerm, id)
    if term_obj:
        term_obj.last_scraped_at = datetime.now(UTC)
        db.commit()
    db.close()