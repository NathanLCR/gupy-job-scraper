import importlib

from sqlalchemy import create_engine, inspect

from entities import Job
from tests.fixtures.legacy_create_all_schema import (
    alembic_downgrade,
    alembic_upgrade_head,
)


def test_job_model_exposes_retrieval_metadata():
    assert {"search_document", "embedding_model", "embedding_updated_at"} <= {
        column.name for column in Job.__table__.columns
    }


def test_retrieval_migration_follows_runtime_schema():
    migration = importlib.import_module(
        "migrations.versions.0012_postgres_indexed_retrieval"
    )
    assert migration.revision == "0012_postgres_indexed_retrieval"
    assert migration.down_revision == "0011_runtime_schema_authority"


def test_sqlite_retrieval_columns_upgrade_and_downgrade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retrieval.db'}")
    alembic_upgrade_head(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert {"search_document", "embedding_model", "embedding_updated_at"} <= columns

    alembic_downgrade(engine, "0011_runtime_schema_authority")
    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert "search_document" not in columns
    assert "embedding_model" not in columns
    assert "embedding_updated_at" not in columns
