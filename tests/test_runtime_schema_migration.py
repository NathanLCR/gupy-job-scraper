import importlib
import inspect
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text

from tests.fixtures.legacy_create_all_schema import (
    build_legacy_create_all_schema,
    alembic_stamp,
    alembic_upgrade_head,
    alembic_downgrade,
    column_is_not_null,
    table_exists,
)


def test_all_revision_ids_fit_alembic_version_column():
    """Assert every revision and down_revision string in migrations/versions/ is <= 32 characters."""
    versions_dir = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    migration_files = [f for f in versions_dir.glob("*.py") if f.name != "__init__.py"]
    assert len(migration_files) > 0, "No migration files found"

    for file_path in migration_files:
        module_name = f"migrations.versions.{file_path.stem}"
        module = importlib.import_module(module_name)
        revision = getattr(module, "revision", None)
        down_revision = getattr(module, "down_revision", None)

        if revision is not None:
            assert len(revision) <= 32, f"Revision {revision} in {file_path.name} exceeds 32 chars ({len(revision)})"
        if down_revision is not None:
            if isinstance(down_revision, tuple):
                for dr in down_revision:
                    assert len(dr) <= 32, f"Down revision {dr} in {file_path.name} exceeds 32 chars ({len(dr)})"
            else:
                assert len(down_revision) <= 32, f"Down revision {down_revision} in {file_path.name} exceeds 32 chars ({len(down_revision)})"


def test_runtime_schema_revision_declares_missing_runtime_objects():
    migration = importlib.import_module(
        "migrations.versions.0011_runtime_schema_authority"
    )
    source = inspect.getsource(migration.upgrade)
    assert migration.down_revision == "0010_pgvector_taxonomies"
    assert "admin_sessions" in source
    assert "llm_extractions" in source
    assert "source" in source


def test_0011_reconciles_a_create_all_database(tmp_path):
    db_file = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_file}")

    # Build legacy create_all schema without alembic_version
    build_legacy_create_all_schema(engine)

    # Insert a dummy job with NULL source to verify backfill
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (id, job_title, extractor_type, company_id, tech_stack, source, region, country_code, currency) "
                "VALUES (1, 'Software Engineer', 'regex', 1, '[]', NULL, 'Latin America', 'BR', 'BRL')"
            )
        )

    # Stamp at 0010
    alembic_stamp(engine, "0010_pgvector_taxonomies")
    # Upgrade head must succeed
    alembic_upgrade_head(engine)

    assert column_is_not_null(engine, "jobs", "source")
    assert column_is_not_null(engine, "jobs_posts", "source")
    assert table_exists(engine, "admin_sessions")
    assert table_exists(engine, "llm_extractions")

    # Verify NULL was backfilled to 'gupy'
    with engine.connect() as conn:
        val = conn.execute(text("SELECT source FROM jobs WHERE id = 1")).scalar()
        assert val == "gupy"

    alembic_downgrade(engine, "0010_pgvector_taxonomies")
    assert table_exists(engine, "admin_sessions")
    assert table_exists(engine, "llm_extractions")


def test_0011_fresh_database_upgrade_downgrade_roundtrip(tmp_path):
    db_file = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_file}")

    # Empty DB -> upgrade head
    alembic_upgrade_head(engine)
    assert table_exists(engine, "admin_sessions")
    assert table_exists(engine, "llm_extractions")
    assert column_is_not_null(engine, "jobs", "source")
    assert column_is_not_null(engine, "jobs_posts", "source")

    # Downgrade to 0010
    alembic_downgrade(engine, "0010_pgvector_taxonomies")
    assert not table_exists(engine, "admin_sessions")
    assert not table_exists(engine, "llm_extractions")

    # Upgrade head again
    alembic_upgrade_head(engine)
    assert table_exists(engine, "admin_sessions")
    assert table_exists(engine, "llm_extractions")
