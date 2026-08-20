import os
from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from entities.base import Base

_engine = None
_async_engine = None
_session_factory = None
_async_session_factory = None


def get_database_url() -> str:
    return settings.get_sync_database_url()


def get_async_database_url() -> str:
    return settings.get_async_database_url()


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, echo=False, connect_args=connect_args)
    return _engine


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        url = get_async_database_url()
        _async_engine = create_async_engine(url, echo=False)
    return _async_engine


def SessionLocal() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
        )
    return _session_factory()


def AsyncSessionLocal() -> AsyncSession:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _async_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding an AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db() -> Generator[Session, None, None]:
    """Sync context generator for workers and background scripts."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates database tables synchronously and applies lightweight column migrations."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    # Lightweight runtime column migration for existing tables
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        with engine.begin() as conn:
            if "jobs_posts" in table_names:
                cols = [c["name"] for c in inspector.get_columns("jobs_posts")]
                if "source" not in cols:
                    conn.execute(text("ALTER TABLE jobs_posts ADD COLUMN source VARCHAR(50) DEFAULT 'gupy'"))

            if "jobs" in table_names:
                cols = [c["name"] for c in inspector.get_columns("jobs")]
                if "source" not in cols:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN source VARCHAR(50) DEFAULT 'gupy'"))
    except Exception as exc:
        # Non-fatal if DB doesn't support or already migrated
        pass
