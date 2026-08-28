"""
Comprehensive Test Suite for Spec 08 (Fail-Closed Operator Security).
Tests:
1. Startup configuration refusal in production (entropy, debug, auth enabled)
2. Fail-closed authentication & authorization for operator routes
3. Session cookie generation (HttpOnly, SameSite=Strict), revocation on logout
4. Query-string and X-Admin-Key rejection
5. Rate limiting on failed login attempts (5 failures -> 429)
6. Route authorization inventory (all mutations require auth, public reads stay open)
7. Operator console document (/nathan-eh-foda) is reachable without a session
   (it fails closed client-side and initiates no admin request), while the
   old `/frontend/admin.html` static path is gone entirely
8. Session store durability: sessions survive across independent store
   instances (the property an in-process dictionary cannot provide)
"""

import pytest
from fastapi.testclient import TestClient
import logging

from app import app
from config import Settings, settings
from api.v1.auth import AdminSessionStore, session_store, _FAILED_LOGINS

TEST_ADMIN_KEY = "test-operator-entropy-secret-key-32-chars-long"


@pytest.fixture(autouse=True)
def reset_auth_state():
    """Reset settings and session store before each test."""
    original_key = settings.ADMIN_API_KEY
    original_enabled = settings.ADMIN_AUTH_ENABLED
    original_env = settings.ENVIRONMENT
    original_debug = settings.DEBUG

    settings.ADMIN_API_KEY = TEST_ADMIN_KEY
    settings.ADMIN_AUTH_ENABLED = True
    settings.ENVIRONMENT = "test"
    settings.DEBUG = False
    session_store.clear()
    _FAILED_LOGINS.clear()

    yield

    settings.ADMIN_API_KEY = original_key
    settings.ADMIN_AUTH_ENABLED = original_enabled
    settings.ENVIRONMENT = original_env
    settings.DEBUG = original_debug
    session_store.clear()
    _FAILED_LOGINS.clear()


# ─── 1. Production Configuration Startup Refusal ─────────────────────────────

def test_production_startup_refuses_disabled_auth():
    prod_settings = Settings(ENVIRONMENT="production", ADMIN_AUTH_ENABLED=False, ADMIN_API_KEY="a"*32, DEBUG=False)
    with pytest.raises(RuntimeError, match="ADMIN_AUTH_ENABLED must be True"):
        prod_settings.validate_security_config()


def test_production_startup_refuses_missing_secret():
    prod_settings = Settings(ENVIRONMENT="production", ADMIN_AUTH_ENABLED=True, ADMIN_API_KEY=None, DEBUG=False)
    with pytest.raises(RuntimeError, match="ADMIN_API_KEY must be configured"):
        prod_settings.validate_security_config()


def test_production_startup_refuses_short_secret():
    prod_settings = Settings(ENVIRONMENT="production", ADMIN_AUTH_ENABLED=True, ADMIN_API_KEY="short-secret", DEBUG=False)
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        prod_settings.validate_security_config()


def test_production_startup_refuses_debug_mode():
    prod_settings = Settings(ENVIRONMENT="production", ADMIN_AUTH_ENABLED=True, ADMIN_API_KEY="a"*32, DEBUG=True)
    with pytest.raises(RuntimeError, match="DEBUG must be False"):
        prod_settings.validate_security_config()


def test_production_startup_accepts_valid_config():
    prod_settings = Settings(ENVIRONMENT="production", ADMIN_AUTH_ENABLED=True, ADMIN_API_KEY="a"*32, DEBUG=False)
    # Should not raise
    prod_settings.validate_security_config()


# ─── 2. Fail-Closed Authentication & Session Handling ────────────────────────

def test_verify_fails_closed_when_unauthenticated():
    client = TestClient(app)
    res = client.get("/api/v1/admin/verify")
    assert res.status_code == 401
    assert "application/json" in res.headers["content-type"]
    assert res.headers.get("cache-control") == "no-store"
    data = res.json()
    assert "Unauthorized" in data["detail"]


def test_verify_rejects_legacy_x_admin_key_header():
    client = TestClient(app)
    res = client.get("/api/v1/admin/verify", headers={"X-Admin-Key": TEST_ADMIN_KEY})
    assert res.status_code == 401


def test_verify_rejects_query_string_credentials():
    client = TestClient(app)
    for q in [f"?token={TEST_ADMIN_KEY}", f"?key={TEST_ADMIN_KEY}", f"?admin_key={TEST_ADMIN_KEY}"]:
        res = client.get(f"/api/v1/admin/verify{q}")
        assert res.status_code == 401


def test_verify_succeeds_with_bearer_token():
    client = TestClient(app)
    res = client.get("/api/v1/admin/verify", headers={"Authorization": f"Bearer {TEST_ADMIN_KEY}"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authenticated"
    assert data["authenticated"] is True
    assert res.headers.get("cache-control") == "no-store"


def test_login_flow_sets_httponly_cookie_and_does_not_echo_secret():
    client = TestClient(app)
    res = client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authenticated"
    assert data["authenticated"] is True
    assert "token" not in data  # Token/secret must not be returned in body
    assert TEST_ADMIN_KEY not in res.text

    # Cookie check
    cookie_header = res.headers.get("set-cookie", "")
    assert settings.ADMIN_SESSION_COOKIE in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header.lower() or "samesite=strict" in cookie_header.lower()

    # Now verify using the session cookie
    verify_res = client.get("/api/v1/admin/verify")
    assert verify_res.status_code == 200
    assert verify_res.json()["authenticated"] is True


def test_logout_invalidates_session_and_clears_cookie():
    client = TestClient(app)
    login_res = client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})
    assert login_res.status_code == 200

    # Logout
    logout_res = client.post("/api/v1/admin/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"

    # Subsequent verify must fail
    verify_res = client.get("/api/v1/admin/verify")
    assert verify_res.status_code == 401


def test_login_rate_limiting():
    client = TestClient(app)
    # 5 failed attempts
    for _ in range(5):
        res = client.post("/api/v1/admin/login", json={"key": "wrong-secret"})
        assert res.status_code == 401

    # 6th attempt must be 429 Too Many Requests
    rate_limited_res = client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})
    assert rate_limited_res.status_code == 429
    assert "Too many failed login attempts" in rate_limited_res.json()["detail"]
    assert "Retry-After" in rate_limited_res.headers


def test_failed_login_audit_event_never_logs_the_credential(caplog):
    client = TestClient(app)
    supplied_secret = "do-not-log-this-operator-secret"

    with caplog.at_level(logging.INFO, logger="skillpulse.audit"):
        res = client.post("/api/v1/admin/login", json={"key": supplied_secret})

    assert res.status_code == 401
    audit_output = "\n".join(caplog.messages)
    assert "event=operator_login" in audit_output
    assert "result=failure" in audit_output
    assert supplied_secret not in audit_output


def test_authenticated_mutation_attempt_is_audited_without_executing_it(caplog):
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="skillpulse.audit"):
        res = client.post(
            "/api/v1/search-terms",
            headers={"Authorization": f"Bearer {TEST_ADMIN_KEY}"},
            json={},
        )

    assert res.status_code == 422
    audit_output = "\n".join(caplog.messages)
    assert "event=operator_mutation" in audit_output
    assert "method=POST" in audit_output
    assert "path=/api/v1/search-terms" in audit_output
    assert "result=422" in audit_output
    assert TEST_ADMIN_KEY not in audit_output


# ─── 3. Route Authorization Matrix ───────────────────────────────────────────

@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/v1/extract", {"text": "Python", "extractor_type": "regex"}),
    ("POST", "/api/v1/jobs/ingest", {"source": "remotive", "term": "python"}),
    ("GET", "/api/v1/jobs/export", None),
    ("GET", "/api/v1/jobs/posts/export", None),
    ("POST", "/api/v1/extract/batch", None),
    ("GET", "/api/v1/extract/status", None),
    ("POST", "/api/v1/match/explain", {"resume_text": "private profile", "job_id": 1}),
    ("POST", "/api/v1/match/profile", {"raw_resume_text": "private profile"}),
    ("GET", "/api/v1/match/profile/1", None),
    ("POST", "/api/v1/analytics/normalize", {"skills": ["Python"]}),
    ("GET", "/api/v1/stats", None),
    ("POST", "/api/v1/search-terms", {"term": "rust", "is_active": True}),
    ("PUT", "/api/v1/search-terms/1", {"term": "rust", "is_active": False}),
    ("DELETE", "/api/v1/search-terms/1", None),
    ("GET", "/api/v1/errors", None),
    ("POST", "/scrape/start", None),
    ("GET", "/scrape/status", None),
    ("POST", "/regex-extract", None),
    ("GET", "/regex-extract/status", None),
    ("POST", "/llm-extract", None),
    ("GET", "/llm-extract/status", None),
    ("GET", "/job-posts", None),
    ("GET", "/job-posts/1", None),
    ("GET", "/search-terms", None),
    ("GET", "/stats", None),
])
def test_sensitive_routes_require_authorization(method, path, payload):
    client = TestClient(app)
    if method == "GET":
        res = client.get(path)
    elif method == "POST":
        res = client.post(path, json=payload)
    elif method == "PUT":
        res = client.put(path, json=payload)
    elif method == "DELETE":
        res = client.delete(path)

    assert res.status_code == 401, f"{method} {path} should return 401 when unauthenticated, got {res.status_code}"
    assert "application/json" in res.headers["content-type"]
    assert res.headers.get("cache-control") == "no-store"
    assert res.headers.get("x-content-type-options") == "nosniff"


def test_public_routes_remain_accessible():
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/jobs?page=1&page_size=5").status_code == 200
    assert client.get("/api/v1/analytics/overview").status_code == 200


# ─── 4. Operator Console Document & Static-Mount Exposure ────────────────────
#
# The console document itself (login form + a workspace that starts hidden)
# holds no secret and is safe to serve unconditionally: it fails closed
# client-side and every real admin action/data read stays behind
# require_admin_auth. Gating the document itself behind a session was a
# lockout bug (no unauthenticated route could ever reach the login form),
# and it did not even close the real hole: `frontend/admin.html` was still
# reachable, unauthenticated, through the StaticFiles mount at `/frontend`.
# These tests assert the actual fix: the static mount no longer has the
# files at all, and the console document/assets are served only from the
# separate `operator/` directory via dedicated routes.

def test_frontend_static_mount_no_longer_serves_admin_assets():
    client = TestClient(app)
    for path in ("/frontend/admin.html", "/frontend/admin.js", "/frontend/admin.css"):
        res = client.get(path)
        assert res.status_code == 404, f"{path} must not be served by the /frontend static mount"


def test_operator_login_document_is_distinct_and_reachable_unauthenticated():
    client = TestClient(app)
    res = client.get("/operator/login")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert res.headers.get("cache-control") == "no-store"
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert "frame-ancestors 'none'" in res.headers.get("content-security-policy", "")
    assert "Operator Console Login" in res.text
    assert 'id="admin-key-input"' in res.text
    assert 'id="admin-app-layout"' not in res.text
    assert TEST_ADMIN_KEY not in res.text


def test_operator_console_query_key_grants_no_authenticated_response():
    client = TestClient(app)
    res = client.get(f"/operator?key={TEST_ADMIN_KEY}")
    assert res.status_code == 401
    assert "set-cookie" not in {k.lower() for k in res.headers.keys()}


def test_operator_workspace_and_assets_require_a_session():
    client = TestClient(app)
    for path in ("/operator", "/operator/assets/admin.js", "/operator/assets/admin.css"):
        res = client.get(path)
        assert res.status_code == 401
        assert res.headers.get("cache-control") == "no-store"
        assert res.headers.get("x-content-type-options") == "nosniff"


def test_obscured_and_unknown_operator_paths_are_not_entry_points():
    client = TestClient(app)
    assert client.get("/nathan-eh-foda").status_code == 404
    assert client.get("/nathan-eh-foda/assets/admin.js").status_code == 404
    assert client.get("/operator/assets/index.html").status_code == 401
    assert client.get("/operator/assets/..%2Fapp.py").status_code == 404


def test_operator_console_serves_admin_when_authenticated():
    client = TestClient(app)
    # Login first
    login_res = client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})
    assert login_res.status_code == 200

    # Request session-gated operator console with cookie
    res = client.get("/operator")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert res.headers.get("cache-control") == "no-store"
    assert "Operator Console" in res.text
    assert 'id="admin-app-layout"' in res.text
    assert 'id="admin-key-input"' not in res.text

    js_res = client.get("/operator/assets/admin.js")
    assert js_res.status_code == 200
    assert "javascript" in js_res.headers["content-type"]

    css_res = client.get("/operator/assets/admin.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers["content-type"]

    assert client.get("/operator/assets/index.html").status_code == 404
    assert client.get("/operator/assets/..%2Fapp.py").status_code == 404


# ─── 5. Session Store Durability (Spec 08 §4) ────────────────────────────────
#
# `session_store` is a module-level singleton, so exercising it through
# `client` alone would pass even with the old in-process dict: the same
# object handles every request in a test process. These tests instantiate
# a second, independent `AdminSessionStore` to prove sessions live in the
# shared database, not in whichever store object happens to have created
# them — the property an in-memory dictionary cannot provide.

def test_session_created_by_one_store_instance_is_valid_on_another():
    raw_token = "durability-check-token-a"
    store_a = AdminSessionStore()
    store_b = AdminSessionStore()

    store_a.create_session(raw_token, duration_hours=8)

    assert store_b.validate_session(raw_token) is True


def test_session_revoked_by_one_store_instance_is_invalid_on_another():
    raw_token = "durability-check-token-b"
    store_a = AdminSessionStore()
    store_b = AdminSessionStore()

    store_a.create_session(raw_token, duration_hours=8)
    assert store_b.validate_session(raw_token) is True

    store_b.revoke_session(raw_token)
    assert store_a.validate_session(raw_token) is False


def test_expired_session_is_rejected_even_if_never_revoked():
    from datetime import datetime, timedelta
    from database import SessionLocal
    from entities import AdminSession
    import hashlib

    raw_token = "durability-check-expired-token"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    db = SessionLocal()
    try:
        db.add(AdminSession(token_hash=token_hash, expires_at=datetime.utcnow() - timedelta(seconds=1)))
        db.commit()
    finally:
        db.close()

    assert AdminSessionStore().validate_session(raw_token) is False


# ─── 6. CORS Scoping for the Operator Auth Surface (Spec 08 §7) ──────────────

def test_admin_surface_rejects_cross_origin_preflight_even_from_an_allowed_public_origin():
    client = TestClient(app)
    preview_origin = "https://preview-123.skillpulse.pages.dev"

    # The public CORS policy allows this origin for ordinary read endpoints.
    public_preflight = client.options(
        "/api/v1/jobs",
        headers={"Origin": preview_origin, "Access-Control-Request-Method": "GET"},
    )
    assert public_preflight.headers.get("access-control-allow-origin") == preview_origin

    # The same origin must be rejected for the operator auth surface.
    admin_preflight = client.options(
        "/api/v1/admin/verify",
        headers={"Origin": preview_origin, "Access-Control-Request-Method": "GET"},
    )
    assert admin_preflight.status_code == 400
    assert admin_preflight.headers.get("access-control-allow-origin") is None


# ─── 7. Origin Validation for Cookie-Authenticated Mutations (Spec 08 §7) ────

def test_cookie_authenticated_mutation_rejects_unexpected_origin():
    client = TestClient(app, base_url="https://skillpulse-api.test")
    client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})

    res = client.put(
        "/api/v1/search-terms/999999",
        json={"term": "x", "is_active": True},
        headers={"Origin": "https://evil.example.com"},
    )
    assert res.status_code == 403
    assert "Origin" in res.json()["detail"]


def test_cookie_authenticated_mutation_accepts_matching_same_origin():
    client = TestClient(app, base_url="https://skillpulse-api.test")
    client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})

    # Correct Origin passes the auth/origin check; 404 (no such row) proves
    # it reached the route rather than being rejected at authorization.
    res = client.put(
        "/api/v1/search-terms/999999",
        json={"term": "x", "is_active": True},
        headers={"Origin": "https://skillpulse-api.test"},
    )
    assert res.status_code == 404


def test_cookie_authenticated_mutation_rejects_missing_origin_in_production():
    original_env = settings.ENVIRONMENT
    settings.ENVIRONMENT = "production"
    try:
        client = TestClient(app, base_url="https://skillpulse-api.test")
        client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})
        res = client.put("/api/v1/search-terms/999999", json={"term": "x", "is_active": True})
        assert res.status_code == 403
        assert "Origin" in res.json()["detail"]
    finally:
        settings.ENVIRONMENT = original_env


def test_bearer_authenticated_mutation_is_unaffected_by_origin_header():
    """Non-browser automation (Bearer token) carries no ambient cookie, so it is exempt from Origin validation."""
    client = TestClient(app, base_url="https://skillpulse-api.test")
    res = client.put(
        "/api/v1/search-terms/999999",
        json={"term": "x", "is_active": True},
        headers={"Authorization": f"Bearer {TEST_ADMIN_KEY}", "Origin": "https://evil.example.com"},
    )
    assert res.status_code == 404


def test_get_requests_are_not_subject_to_origin_validation():
    """Only state-changing methods are checked; GET /verify must work with or without an Origin header."""
    client = TestClient(app, base_url="https://skillpulse-api.test")
    client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})

    res = client.get("/api/v1/admin/verify", headers={"Origin": "https://evil.example.com"})
    assert res.status_code == 200


def test_logout_rejects_cross_origin_forged_request():
    client = TestClient(app, base_url="https://skillpulse-api.test")
    client.post("/api/v1/admin/login", json={"key": TEST_ADMIN_KEY})

    res = client.post("/api/v1/admin/logout", headers={"Origin": "https://evil.example.com"})
    assert res.status_code == 403

    # The session must still be intact since the forged logout was rejected.
    verify_res = client.get("/api/v1/admin/verify")
    assert verify_res.status_code == 200
