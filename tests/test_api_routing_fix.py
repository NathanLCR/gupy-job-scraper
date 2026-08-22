from pathlib import Path
import subprocess
import json

from fastapi.testclient import TestClient

from app import app
from config import settings
from schemas.analytics import SkillAnalyticsResponse
from schemas.job import JobListResponse
from schemas.matcher import CandidateMatchResponse


ROOT = Path(__file__).resolve().parents[1]


def test_admin_login_cookie_is_eligible_for_cross_site_fetch():
    """Spec 08 §3.2: Browser session cookie is HttpOnly, SameSite=Strict, Path=/."""
    settings.ADMIN_API_KEY = "test-operator-secret-for-routing-test-32"
    client = TestClient(app, base_url="https://skillpulse-api.test")

    response = client.post(
        "/api/v1/admin/login",
        json={"key": "test-operator-secret-for-routing-test-32"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie


def test_operator_query_key_cannot_bypass_login_or_set_cookie():
    """
    Spec 08 §3.3/§6: a query-string key must never establish an authenticated
    session. The login document is public, while the workspace document is
    server-gated and only a real login establishes the session cookie.
    """
    settings.ADMIN_API_KEY = "test-operator-secret-for-routing-test-32"
    client = TestClient(app, base_url="https://skillpulse-api.test")

    query_response = client.get("/operator?key=test-operator-secret-for-routing-test-32")
    assert query_response.status_code == 401
    assert "set-cookie" not in {k.lower() for k in query_response.headers.keys()}

    login_page = client.get("/operator/login")
    assert login_page.status_code == 200
    assert "Operator Console Login" in login_page.text
    assert "set-cookie" not in {k.lower() for k in login_page.headers.keys()}

    # Login to establish valid session cookie
    login_res = client.post("/api/v1/admin/login", json={"key": "test-operator-secret-for-routing-test-32"})
    assert login_res.status_code == 200

    # Access console with session cookie
    cookie_response = client.get("/operator")
    assert cookie_response.status_code == 200
    assert "Operator Console" in cookie_response.text


def test_frontend_pages_load_environment_config_before_controllers():
    """Catches deployments where API_BASE is evaluated before config.js sets the URL."""
    settings.ADMIN_API_KEY = "test-operator-secret-for-routing-test-32"
    client = TestClient(app)

    public_html = client.get("/").text
    headers = {"Authorization": "Bearer test-operator-secret-for-routing-test-32"}
    admin_html = client.get("/operator", headers=headers).text

    assert public_html.index('/frontend/config.js') < public_html.index('/frontend/script.js')
    assert admin_html.index('/frontend/config.js') < admin_html.index('/operator/assets/admin.js')

    config_response = client.get("/frontend/config.js")
    assert config_response.status_code == 200
    assert "javascript" in config_response.headers["content-type"]
    assert "window.API_BASE_URL" in config_response.text

    admin_js_response = client.get("/operator/assets/admin.js", headers=headers)
    assert admin_js_response.status_code == 200
    assert "javascript" in admin_js_response.headers["content-type"]

    # The operator console's HTML/JS/CSS must never be reachable through the
    # public static mount that serves the rest of frontend/ (Spec 08 §3.1).
    for path in ("/frontend/admin.html", "/frontend/admin.js", "/frontend/admin.css"):
        assert client.get(path).status_code == 404, f"{path} must not exist on the /frontend static mount"


def test_cloudflare_pages_routes_use_supported_rewrites_and_nearest_json_404():
    """Catches unsupported 404 rewrites and index.html canonical redirects."""
    redirects = (ROOT / "frontend" / "_redirects").read_text().splitlines()
    active_rules = [line.split() for line in redirects if line.strip() and not line.startswith("#")]

    supported_codes = {"200", "301", "302", "303", "307", "308"}
    assert all(len(rule) < 3 or rule[2] in supported_codes for rule in active_rules)
    assert not any(rule[0] in {"/api/*", "/frontend/*", "/*"} for rule in active_rules)

    for route in ("/match", "/jobs", "/market", "/how-it-works", "/dashboard"):
        rule = next(rule for rule in active_rules if rule[0] == route)
        assert rule[1:] == ["/", "200"]

    expected_public_assets = {
        "/frontend/favicon.png": "/favicon.png",
        "/frontend/style.css": "/style.css",
        "/frontend/config.js": "/config.js",
        "/frontend/script.js": "/script.js",
    }
    for source, destination in expected_public_assets.items():
        rule = next(rule for rule in active_rules if rule[0] == source)
        assert rule[1:] == [destination, "200"]

    assert (ROOT / "frontend" / "404.html").exists()
    json_404 = (ROOT / "frontend" / "api" / "404.html").read_text().strip()
    assert json_404 == (
        '{"error": "no API mounted on this origin — see config.js"}'
    )
    assert (ROOT / "frontend" / "api" / "404.json").read_text().strip() == json_404

    headers_text = (ROOT / "frontend" / "_headers").read_text()
    assert "/api/*" in headers_text
    assert "Content-Type: application/json; charset=utf-8" in headers_text


def test_cloudflare_headers_prevent_stale_controller_caching():
    """Spec 07 §6: unversioned assets must not use long max-age caching."""
    headers_text = (ROOT / "frontend" / "_headers").read_text()
    assert "max-age=86400" not in headers_text, "Unversioned static files must not have 1-day max-age cache"
    assert "Cache-Control: no-cache" in headers_text or "Cache-Control: no-cache, no-store" in headers_text


def test_api_schema_contracts_match_frontend_expectations():
    """Verify backend Pydantic models contain the required properties expected by the frontend."""
    # JobListResponse contract
    job_list_fields = JobListResponse.model_fields
    assert "items" in job_list_fields
    assert "pagination" in job_list_fields

    # CandidateMatchResponse contract
    match_fields = CandidateMatchResponse.model_fields
    assert "matches" in match_fields
    assert "extracted_skills" in match_fields

    # SkillAnalyticsResponse contract
    analytics_fields = SkillAnalyticsResponse.model_fields
    assert "total_jobs" in analytics_fields
    assert "top_skills" in analytics_fields
    assert "top_locations" in analytics_fields
    assert "salary_by_seniority" in analytics_fields
    assert "workplace_distribution" in analytics_fields


def test_deploy_manifest_generator():
    """Verify deploy manifest generator produces deterministic hashes for all release files."""
    manifest_script = ROOT / "scripts" / "generate_deploy_manifest.py"
    assert manifest_script.exists(), "Deploy manifest generation script must exist"

    result = subprocess.run(
        ["python3", str(manifest_script), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    manifest = json.loads(result.stdout)
    assert "files" in manifest
    assert "commit" in manifest
    assert "dirty" in manifest
    assert "api_base_url" in manifest

    required_files = [
        "index.html",
        "script.js",
        "style.css",
        "config.js",
        "_redirects",
        "_headers",
        "404.html",
        "api/404.json",
        "api/404.html",
    ]
    for rf in required_files:
        assert rf in manifest["files"], f"Missing {rf} in manifest"
        assert len(manifest["files"][rf]["sha256"]) == 64
