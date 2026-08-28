import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from config import settings
from app import app
from services.readiness_service import ReadinessResult


client = TestClient(app)


def test_liveness_never_calls_readiness(monkeypatch):
    monkeypatch.setattr("app.check_database_readiness", Mock(side_effect=AssertionError("Readiness should not be called")))
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "SkillPulse"
    assert "version" in data


def test_readiness_returns_503_when_database_is_unavailable(monkeypatch):
    unavailable_result = ReadinessResult(
        ready=False,
        database="unavailable",
        schema_state="unknown",
        failure_category="database_connection_failed",
        public_message="Database is unavailable.",
    )
    monkeypatch.setattr("app.check_database_readiness", lambda: unavailable_result)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.headers.get("cache-control") == "no-store"
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["database"] == "unavailable"
    assert data["schema"] == "unknown"


def test_health_compatibility_alias_matches_readiness(monkeypatch):
    unavailable_result = ReadinessResult(
        ready=False,
        database="unavailable",
        schema_state="unknown",
        failure_category="database_connection_failed",
        public_message="Database is unavailable.",
    )
    monkeypatch.setattr("app.check_database_readiness", lambda: unavailable_result)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.headers.get("cache-control") == "no-store"
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
        "schema": "unknown",
        "version": settings.VERSION,
    }


def test_readiness_returns_200_when_database_is_ready(monkeypatch):
    ready_result = ReadinessResult(
        ready=True,
        database="connected",
        schema_state="current",
    )
    monkeypatch.setattr("app.check_database_readiness", lambda: ready_result)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["schema"] == "current"
    assert data["version"] == settings.VERSION


@pytest.mark.asyncio
async def test_lifespan_production_raises_on_unavailable_readiness(monkeypatch):
    from app import lifespan
    unavailable_result = ReadinessResult(
        ready=False,
        database="unavailable",
        schema_state="unknown",
        failure_category="database_connection_failed",
        public_message="Database is unavailable.",
    )
    monkeypatch.setattr("app.check_database_readiness", lambda: unavailable_result)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "a" * 32)
    monkeypatch.setattr(settings, "ADMIN_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://user:pass@localhost:5432/db")

    with pytest.raises(RuntimeError, match="Startup readiness failed: database_connection_failed"):
        async with lifespan(app):
            pass


def test_database_init_endpoint_is_removed():
    response = client.post("/database/init", json={})
    assert response.status_code == 404
