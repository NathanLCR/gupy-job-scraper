from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from app import app
from config import settings
from services.rate_limit_service import RateLimitDecision, RateLimitUnavailableError


class TrackingLimiter:
    def __init__(self):
        self.counts = defaultdict(int)
        self.seen_subjects = []

    def _decision(self, subject, limit):
        count = self.counts[subject]
        return RateLimitDecision(
            allowed=count < limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=900 if count >= limit else 0,
            reset_after_seconds=900 if count else 0,
        )

    def peek(self, scope, subject, limit, window_seconds):
        assert scope == "operator_login_failure"
        assert window_seconds == 900
        self.seen_subjects.append(subject)
        return self._decision(subject, limit)

    def record(self, scope, subject, limit, window_seconds):
        self.counts[subject] += 1
        return self._decision(subject, limit)

    def clear(self, scope, subject):
        self.counts.pop(subject, None)


@pytest.fixture
def login_context(monkeypatch):
    from api.v1 import auth

    limiter = TrackingLimiter()
    monkeypatch.setattr(auth, "get_rate_limiter", lambda: limiter, raising=False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "operator-test-secret-key-at-least-32")
    monkeypatch.setattr(settings, "ADMIN_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_KEY_SALT", "login-test-salt-that-is-at-least-32-characters")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "[]")
    monkeypatch.setattr(settings, "TRUST_CLOUDFLARE_CONNECTING_IP", False)
    return limiter


def test_failed_logins_share_one_distributed_bucket(login_context):
    first = TestClient(app)
    second = TestClient(app)
    for client in (first, first, first, second, second):
        assert client.post("/api/v1/admin/login", json={"key": "wrong"}).status_code == 401

    blocked = first.post(
        "/api/v1/admin/login",
        json={"key": settings.ADMIN_API_KEY},
        headers={"X-Request-ID": "login-limit-request"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded. Please try again later."
    assert blocked.headers["retry-after"] == "900"


def test_success_clears_only_that_login_subject(login_context):
    client = TestClient(app)
    for _ in range(2):
        assert client.post("/api/v1/admin/login", json={"key": "wrong"}).status_code == 401
    assert client.post(
        "/api/v1/admin/login", json={"key": settings.ADMIN_API_KEY}
    ).status_code == 200

    for _ in range(5):
        assert client.post("/api/v1/admin/login", json={"key": "wrong"}).status_code == 401


def test_untrusted_caller_cannot_rotate_forwarding_headers(login_context):
    client = TestClient(app)
    for index in range(5):
        response = client.post(
            "/api/v1/admin/login",
            json={"key": "wrong"},
            headers={
                "CF-Connecting-IP": f"198.51.100.{index + 1}",
                "X-Forwarded-For": f"203.0.113.{index + 1}",
            },
        )
        assert response.status_code == 401
    assert len(set(login_context.seen_subjects)) == 1
    assert client.post(
        "/api/v1/admin/login", json={"key": settings.ADMIN_API_KEY}
    ).status_code == 429


def test_login_fails_closed_when_redis_is_unavailable(login_context, monkeypatch):
    from api.v1 import auth

    def unavailable():
        raise RateLimitUnavailableError("redis://user:secret@private-host:6379/0")

    monkeypatch.setattr(auth, "get_rate_limiter", unavailable)
    response = TestClient(app).post(
        "/api/v1/admin/login", json={"key": settings.ADMIN_API_KEY}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Login service temporarily unavailable."
    assert response.headers["cache-control"] == "no-store"
