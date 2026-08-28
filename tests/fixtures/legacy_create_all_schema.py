from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from entities.base import Base


def get_alembic_config(engine: Engine) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return alembic_cfg


def alembic_stamp(engine: Engine, revision: str) -> None:
    cfg = get_alembic_config(engine)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.stamp(cfg, revision)


def alembic_upgrade_head(engine: Engine) -> None:
    cfg = get_alembic_config(engine)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def alembic_downgrade(engine: Engine, revision: str) -> None:
    cfg = get_alembic_config(engine)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, revision)


def table_exists(engine: Engine, table_name: str) -> bool:
    inspector = inspect(engine)
    return inspector.has_table(table_name)


def column_is_not_null(engine: Engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    for col in inspector.get_columns(table_name):
        if col["name"] == column_name:
            return not col.get("nullable", True)
    return False


def build_legacy_create_all_schema(engine: Engine) -> None:
    """
    Builds the database the way the retired lifespan did:
    1. Runs migration chain up to 0010_pgvector_taxonomies.
    2. Adds NULLABLE jobs.source and jobs_posts.source via runtime ALTER TABLE.
    3. Creates admin_sessions and llm_extractions tables.
    4. Drops alembic_version table so no version stamp exists.
    """
    cfg = get_alembic_config(engine)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0010_pgvector_taxonomies")

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE jobs ADD COLUMN source VARCHAR(50) DEFAULT 'gupy'"))
        conn.execute(text("ALTER TABLE jobs_posts ADD COLUMN source VARCHAR(50) DEFAULT 'gupy'"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    # Create admin_sessions and llm_extractions as Base.metadata.create_all did
    Base.metadata.tables["admin_sessions"].create(bind=engine, checkfirst=True)
    Base.metadata.tables["llm_extractions"].create(bind=engine, checkfirst=True)
