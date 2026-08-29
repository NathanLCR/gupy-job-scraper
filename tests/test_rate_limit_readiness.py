from unittest.mock import Mock

from fastapi.testclient import TestClient

from app import app
from config import settings
from services import readiness_service as readiness
from services.readiness_service import DependencyReadiness, ReadinessResult


client = TestClient(app)


def test_redis_outage_keeps_database_readiness_200_but_reports_degraded(monkeypatch):
    database = ReadinessResult(True, "connected", "current")
    redis_state = DependencyReadiness(status="degraded")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr("app.check_database_readiness", lambda: database)
    monkeypatch.setattr("app.check_redis_readiness", lambda: redis_state, raising=False)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["dependencies"] == {
        "database": "connected",
        "redis": "degraded",
    }


def test_database_outage_remains_gating_when_redis_is_connected(monkeypatch):
    database = ReadinessResult(False, "unavailable", "unknown")
    monkeypatch.setattr("app.check_database_readiness", lambda: database)
    monkeypatch.setattr(
        "app.check_redis_readiness",
        lambda: DependencyReadiness(status="connected"),
        raising=False,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"]["redis"] == "connected"


def test_liveness_never_checks_redis(monkeypatch):
    monkeypatch.setattr(
        "app.check_redis_readiness",
        Mock(side_effect=AssertionError("Redis must not gate liveness")),
        raising=False,
    )
    assert client.get("/health/live").status_code == 200


def test_redis_readiness_redacts_connection_failure(monkeypatch, caplog):
    class BrokenRedis:
        def ping(self):
            raise RuntimeError("redis://user:secret@private-cache.internal:6379/0")

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://ignored.invalid:6379/0")
    monkeypatch.setattr(
        readiness.redis.Redis,
        "from_url",
        lambda *args, **kwargs: BrokenRedis(),
        raising=False,
    )

    state = readiness.check_redis_readiness(timeout_seconds=0.1)

    assert state.status == "degraded"
    assert "secret" not in caplog.text
    assert "private-cache" not in caplog.text
