from sqlalchemy import select, insert, update
from database import SessionLocal
from entities.search_term import SearchTerm

def get_search_terms():
    stm = select(SearchTerm).where(SearchTerm.is_active.is_(True))
    terms = SessionLocal().scalars(stm).all()
    return terms

def add_search_term(term):
    db = SessionLocal()
    stm = insert(SearchTerm).values(term=term)
    db.execute(stm)
    db.commit()
    db.close()

def remove_search_term(id):
    db = SessionLocal()
    find_query = select(SearchTerm.id).where(SearchTerm.id == id)
    term = db.execute(find_query).scalar_one_or_none()
    if term is None:
        raise ValueError("Search term not found")
    update_query = update(SearchTerm).where(SearchTerm.id == id).values(is_active=False)
    db.execute(update_query)
    db.commit()
    db.close()
    return term