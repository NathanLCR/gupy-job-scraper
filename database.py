from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from entities import Base


DATABASE_URL = "sqlite:///jobs.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
