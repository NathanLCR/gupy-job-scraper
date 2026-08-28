import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app import app
from config import settings
from services.rate_limit_policy import RateLimitPolicy, resolve_rate_limit_policy
from services.rate_limit_service import (
    RedisRateLimiter,
    RateLimitDecision,
    RateLimitUnavailableError,
)


class MockRateLimiter:
    """Configurable mock limiter for testing middleware policy and HTTP contracts."""

    def __init__(self, limit: int | None = None, window_seconds: int = 60):
        self.enforced_limit = limit
        self.window_seconds = window_seconds
        self.calls: list[tuple[str, str, int, int]] = []
        self.count = 0
        self.should_fail = False

    def check(self, scope: str, subject_digest: str, limit: int, window_seconds: int) -> RateLimitDecision:
        effective_limit = self.enforced_limit if self.enforced_limit is not None else limit
        self.calls.append((scope, subject_digest, effective_limit, window_seconds))
        if self.should_fail:
            raise RateLimitUnavailableError("Redis connection lost")

        self.count += 1
        allowed = self.count <= effective_limit
        remaining = max(0, effective_limit - self.count)
        retry_after = 0 if allowed else 42
        reset_after = 60
        return RateLimitDecision(
            allowed=allowed,
            limit=effective_limit,
            remaining=remaining,
            retry_after_seconds=retry_after,
            reset_after_seconds=reset_after,
        )


@pytest.fixture(autouse=True)
def enable_rate_limiting():
    orig_enabled = settings.RATE_LIMIT_ENABLED
    orig_shadow = settings.RATE_LIMIT_SHADOW
    settings.RATE_LIMIT_ENABLED = True
    settings.RATE_LIMIT_SHADOW = False
    yield
    settings.RATE_LIMIT_ENABLED = orig_enabled
    settings.RATE_LIMIT_SHADOW = orig_shadow



@pytest.mark.parametrize(
    "path,scope,expected_limit",
    [
        ("/api/v1/jobs/search/hybrid", "public_search", 60),
        ("/api/v1/jobs/search", "public_search", 60),
        ("/api/v1/match", "public_match", 20),
        ("/api/v1/match/explain", "ai_explain", 5),
        ("/api/v1/extract", "ai_extract", 10),
    ],
)
def test_policy_maps_normalized_route_groups(path, scope, expected_limit):
    policy = resolve_rate_limit_policy("POST", path)
    assert policy is not None
    assert policy.scope == scope
    assert policy.limit == expected_limit
    assert policy.window_seconds == 60


@pytest.mark.parametrize(
    "path,scope",
    [
        ("/api/v1/match/", "public_match"),
        ("/api/v1/match/explain/", "ai_explain"),
        ("/api/v1/extract/", "ai_extract"),
    ],
)
def test_policy_ignores_trailing_slash(path, scope):
    policy = resolve_rate_limit_policy("POST", path)
    assert policy is not None
    assert policy.scope == scope


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/jobs"),
        ("GET", "/api/v1/analytics/overview"),
        ("GET", "/health"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("POST", "/api/v1/unknown"),
        ("POST", "/health"),
    ],
)
def test_policy_unmetered_for_get_health_and_unlisted(method, path):
    assert resolve_rate_limit_policy(method, path) is None


def test_allowed_requests_attach_rate_limit_headers(monkeypatch):
    mock_limiter = MockRateLimiter()
    monkeypatch.setattr("app.get_rate_limiter", lambda: mock_limiter)

    client = TestClient(app)
    res = client.post(
        "/api/v1/match",
        json={"resume_text": "Python engineer", "target_region": "Europe", "limit": 2},
    )
    assert res.status_code == 200
    assert res.headers.get("RateLimit-Limit") == "20"
    assert res.headers.get("RateLimit-Remaining") == "19"
    assert res.headers.get("RateLimit-Reset") == "60"


def test_rejected_request_returns_429_contract(monkeypatch):
    mock_limiter = MockRateLimiter(limit=1)
    monkeypatch.setattr("app.get_rate_limiter", lambda: mock_limiter)

    client = TestClient(app)
    payload = {"resume_text": "Python engineer", "target_region": "Europe", "limit": 2}

    # 1st request allowed
    res1 = client.post("/api/v1/match", json=payload)
    assert res1.status_code == 200

    # 2nd request rejected
    res2 = client.post("/api/v1/match", json=payload)
    assert res2.status_code == 429
    assert "application/json" in res2.headers.get("content-type", "")
    assert res2.headers.get("cache-control") == "no-store"
    assert res2.headers.get("retry-after") == "42"

    body = res2.json()
    assert body["detail"] == "Rate limit exceeded. Please try again later."
    assert body["retry_after_seconds"] == 42
    assert "request_id" in body


def test_direct_untrusted_spoofed_headers_resolve_to_same_subject(monkeypatch):
    mock_limiter = MockRateLimiter(limit=1)
    monkeypatch.setattr("app.get_rate_limiter", lambda: mock_limiter)

    client = TestClient(app)
    payload = {"resume_text": "Python engineer", "target_region": "Europe", "limit": 2}

    # 1st request with spoofed headers
    res1 = client.post(
        "/api/v1/match",
        json=payload,
        headers={"X-Forwarded-For": "1.1.1.1", "CF-Connecting-IP": "2.2.2.2"},
    )
    assert res1.status_code == 200

    # 2nd request with different spoofed headers from untrusted connection
    res2 = client.post(
        "/api/v1/match",
        json=payload,
        headers={"X-Forwarded-For": "9.9.9.9", "CF-Connecting-IP": "8.8.8.8"},
    )
    assert res2.status_code == 429
    # Verify both calls checked the exact same subject digest
    assert len(mock_limiter.calls) == 2
    assert mock_limiter.calls[0][1] == mock_limiter.calls[1][1]


def test_redis_failure_fails_closed_with_503(monkeypatch):
    mock_limiter = MockRateLimiter()
    mock_limiter.should_fail = True
    monkeypatch.setattr("app.get_rate_limiter", lambda: mock_limiter)

    client = TestClient(app)
    res = client.post(
        "/api/v1/match",
        json={"resume_text": "Python engineer", "target_region": "Europe", "limit": 2},
    )
    assert res.status_code == 503
    assert "application/json" in res.headers.get("content-type", "")
    assert res.headers.get("cache-control") == "no-store"
    assert "request_id" in res.json()


def test_shadow_mode_lets_would_be_denied_requests_through(monkeypatch):
    mock_limiter = MockRateLimiter(limit=0)  # Always denied
    monkeypatch.setattr("app.get_rate_limiter", lambda: mock_limiter)
    monkeypatch.setattr(settings, "RATE_LIMIT_SHADOW", True)

    client = TestClient(app)
    res = client.post(
        "/api/v1/match",
        json={"resume_text": "Python engineer", "target_region": "Europe", "limit": 2},
    )
    # Under shadow mode, 429 is not returned; endpoint executes normally (200)
    assert res.status_code == 200


def test_unauthenticated_ai_endpoint_consumes_allowance_in_middleware(monkeypatch):
    mock_limiter = MockRateLimiter(limit=1)
    monkeypatch.setattr("app.get_rate_limiter", lambda: mock_limiter)

    client = TestClient(app)
    # 1st attempt: rate limiter allows, but endpoint auth fails (401)
    res1 = client.post("/api/v1/match/explain", json={"job_id": 1, "resume_text": "text"})
    assert res1.status_code == 401

    # 2nd attempt: rate limiter denies (429) before reaching auth
    res2 = client.post("/api/v1/match/explain", json={"job_id": 1, "resume_text": "text"})
    assert res2.status_code == 429
