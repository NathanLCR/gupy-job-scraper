import pytest
import time
from unittest.mock import MagicMock, Mock, patch
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy import create_engine, text

from services import readiness_service as readiness
from tests.fixtures.legacy_create_all_schema import alembic_upgrade_head, alembic_stamp


class BrokenEngine:
    def __init__(self, url="postgresql://user:super_secret_password@db.example.com:5432/proddb"):
        self.url = url

    def connect(self):
        raise OperationalError("SELECT 1", {}, Exception("Connection refused to postgresql://user:super_secret_password@db.example.com:5432/proddb"))


def test_readiness_requires_query_and_current_revision(monkeypatch):
    monkeypatch.setattr(readiness, "get_current_revision", lambda conn: "0011_runtime_schema_authority")
    monkeypatch.setattr(readiness, "get_expected_head", lambda: "0011_runtime_schema_authority")
    
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    monkeypatch.setattr(readiness, "get_engine", lambda: mock_engine)
    
    result = readiness.check_database_readiness()
    assert result.ready is True
    assert result.database == "connected"
    assert result.schema_state == "current"
    assert result.failure_category is None


def test_readiness_hides_internal_error(monkeypatch):
    monkeypatch.setattr(readiness, "get_engine", lambda: BrokenEngine("postgresql://user:super_secret_password@db.example.com:5432/proddb"))
    result = readiness.check_database_readiness()
    assert result.ready is False
    assert result.database == "unavailable"
    assert result.schema_state == "unknown"
    assert result.failure_category == "database_connection_failed"
    assert "super_secret_password" not in (result.public_message or "")
    assert "user:" not in (result.public_message or "")


def test_readiness_timeout(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = TimeoutError("Statement timeout exceeded")
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    monkeypatch.setattr(readiness, "get_engine", lambda: mock_engine)

    result = readiness.check_database_readiness(timeout_seconds=0.1)
    assert result.ready is False
    assert result.database == "unavailable"
    assert result.schema_state == "unknown"
    assert result.failure_category == "database_readiness_timeout"


def test_readiness_missing_revision_table(monkeypatch):
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    monkeypatch.setattr(readiness, "get_engine", lambda: mock_engine)
    monkeypatch.setattr(readiness, "get_current_revision", lambda conn: None)
    monkeypatch.setattr(readiness, "get_expected_head", lambda: "0011_runtime_schema_authority")

    result = readiness.check_database_readiness()
    assert result.ready is False
    assert result.database == "connected"
    assert result.schema_state == "unknown"
    assert result.failure_category == "database_schema_missing"


def test_readiness_stale_revision(monkeypatch):
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    monkeypatch.setattr(readiness, "get_engine", lambda: mock_engine)
    monkeypatch.setattr(readiness, "get_current_revision", lambda conn: "0010_pgvector_taxonomies")
    monkeypatch.setattr(readiness, "get_expected_head", lambda: "0011_runtime_schema_authority")

    result = readiness.check_database_readiness()
    assert result.ready is False
    assert result.database == "connected"
    assert result.schema_state == "outdated"
    assert result.failure_category == "database_schema_outdated"


def test_get_expected_head_loads_from_migrations_directory():
    head = readiness.get_expected_head()
    assert head == "0012_postgres_indexed_retrieval"


def test_readiness_total_deadline_includes_connection_establishment(monkeypatch):
    class SlowEngine:
        def connect(self):
            time.sleep(0.2)
            raise AssertionError("connection completed after the deadline")

    monkeypatch.setattr(readiness, "get_engine", lambda: SlowEngine())
    started = time.monotonic()
    result = readiness.check_database_readiness(timeout_seconds=0.03)
    elapsed = time.monotonic() - started

    assert result.failure_category == "database_readiness_timeout"
    assert elapsed < 0.12
