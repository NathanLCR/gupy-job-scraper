import os
import urllib.parse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from entities import Base
from dotenv import load_dotenv

load_dotenv()

_engine = None
_session_factory = None


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    db_user_raw = os.getenv("DB_USER")
    db_password_raw = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")
    db_sslmode = os.getenv("DB_SSLMODE")

    missing = [
        key
        for key, value in {
            "DB_HOST": db_host,
            "DB_NAME": db_name,
            "DB_USER": db_user_raw,
            "DB_PASSWORD": db_password_raw,
        }.items()
        if not value
    ]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Database configuration is incomplete. Set DATABASE_URL or provide: {missing_str}"
        )

    db_user = urllib.parse.quote_plus(db_user_raw)
    db_password = urllib.parse.quote_plus(db_password_raw)
    database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    if db_sslmode:
        database_url = f"{database_url}?sslmode={urllib.parse.quote_plus(db_sslmode)}"

    return database_url


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), echo=False)
    return _engine


def SessionLocal():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
        )
    return _session_factory()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
