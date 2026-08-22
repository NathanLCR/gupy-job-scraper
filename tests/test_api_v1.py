import pytest
from fastapi.testclient import TestClient
from app import app
from config import settings

client = TestClient(app)


def operator_headers():
    settings.ADMIN_API_KEY = "test-operator-secret-for-api-tests-32"
    return {"Authorization": "Bearer test-operator-secret-for-api-tests-32"}


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["database"] == "connected"


def test_openapi_docs():
    response = client.get("/docs")
    assert response.status_code == 200
    openapi_res = client.get("/openapi.json")
    assert openapi_res.status_code == 200
    openapi_data = openapi_res.json()
    assert "SkillPulse" in openapi_data["info"]["title"]


def test_extract_endpoint():
    payload = {
        "text": "Vaga para Desenvolvedor Python Sênior. Requisitos: 5 anos de experiência com Python, FastAPI, Docker e AWS. Soft skills: boa comunicação e liderança. Diferenciais: Kubernetes.",
        "extractor_type": "regex",
    }
    response = client.post("/api/v1/extract", json=payload, headers=operator_headers())
    assert response.status_code == 200
    data = response.json()
    assert "Python" in data["hard_skills"]
    assert "FastAPI" in data["hard_skills"]
    assert "Docker" in data["hard_skills"]
    assert "Kubernetes" in data["nice_to_have"]
    assert data["seniority"] == "Sênior"
    assert data["years_experience"] == 5


def test_extract_empty_text():
    response = client.post("/api/v1/extract", json={"text": "   "}, headers=operator_headers())
    assert response.status_code == 400


def test_match_endpoint():
    payload = {
        "resume_text": "Experienced Senior Software Engineer with strong background in Python, Django, FastAPI, Docker, and PostgreSQL. Excellent communication and teamwork skills.",
        "target_region": "Global",
        "limit": 5,
        "min_fit_score": 0.0,
    }
    response = client.post("/api/v1/match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "extracted_skills" in data
    assert "Python" in data["extracted_skills"]["hard_skills"]
    assert "matches" in data


def test_create_and_get_candidate_profile():
    payload = {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "raw_resume_text": "Lead Engineer with expertise in Python, Kubernetes, AWS, and Microservices.",
        "target_region": "Europe",
        "target_role": "Lead Architect",
        "seniority": "Lead",
        "years_experience": 8,
    }
    headers = operator_headers()
    response = client.post("/api/v1/match/profile", json=payload, headers=headers)
    assert response.status_code == 201
    profile = response.json()
    assert profile["id"] is not None
    assert profile["name"] == "Jane Doe"
    assert profile["seniority"] == "Lead"

    # Fetch created profile
    get_res = client.get(f"/api/v1/match/profile/{profile['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["email"] == "jane.doe@example.com"


def test_list_jobs_endpoint():
    response = client.get("/api/v1/jobs?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pagination" in data
    assert data["pagination"]["page"] == 1


def test_analytics_skills_endpoint():
    response = client.get("/api/v1/analytics/skills")
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert "top_skills" in data


def test_analytics_graph_endpoint():
    response = client.get("/api/v1/analytics/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


def test_admin_auth_flow():
    settings.ADMIN_API_KEY = "test-operator-secret-for-api-tests-32"
    # 1. Unauthenticated request to protected endpoint should fail with 401
    unauth_res = client.get("/api/v1/errors")
    assert unauth_res.status_code == 401

    # 2. Invalid credentials should fail with 401
    login_fail = client.post("/api/v1/admin/login", json={"key": "wrong-key"})
    assert login_fail.status_code == 401

    # 3. Valid login should succeed and set HttpOnly cookie
    login_ok = client.post("/api/v1/admin/login", json={"key": "test-operator-secret-for-api-tests-32"})
    assert login_ok.status_code == 200
    assert login_ok.json()["status"] == "authenticated"

    # 4. Authenticated request with Bearer header should succeed
    auth_headers = {"Authorization": "Bearer test-operator-secret-for-api-tests-32"}
    verify_res = client.get("/api/v1/admin/verify", headers=auth_headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "authenticated"


def test_search_terms_crud():
    settings.ADMIN_API_KEY = "test-operator-secret-for-api-tests-32"
    headers = {"Authorization": "Bearer test-operator-secret-for-api-tests-32"}
    # 1. Create a search term (requires admin auth)
    term_payload = {"term": "Rust Developer", "is_active": True}
    res = client.post("/api/v1/search-terms", json=term_payload, headers=headers)
    assert res.status_code in [201, 400]  # 400 if already exists in test DB

    # 2. List search terms
    list_res = client.get("/api/v1/search-terms?page=1&page_size=20", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()["items"]) > 0


def test_stats_and_errors_endpoints():
    headers = operator_headers()
    stats_res = client.get("/api/v1/stats", headers=headers)
    assert stats_res.status_code == 200
    assert "jobs_count" in stats_res.json()

    errors_res = client.get("/api/v1/errors", headers=headers)
    assert errors_res.status_code == 200
    assert "items" in errors_res.json()


def test_frontend_routes():
    settings.ADMIN_API_KEY = "test-operator-secret-for-api-tests-32"
    # Public candidate application routes
    for path in ["/", "/match", "/jobs", "/market", "/how-it-works", "/dashboard"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "SkillPulse" in res.text
        assert "Candidate Match" in res.text

    # The login document is public, but the operator workspace and its assets
    # are server-gated. The retired obscured route must stay gone.
    unauth_client = TestClient(app)
    login_page = unauth_client.get("/operator/login")
    assert login_page.status_code == 200
    assert "text/html" in login_page.headers["content-type"]
    assert "Operator Console Login" in login_page.text

    res_admin_unauth = unauth_client.get("/operator")
    assert res_admin_unauth.status_code == 401

    res_admin = unauth_client.get("/operator", headers=operator_headers())
    assert res_admin.status_code == 200
    assert "text/html" in res_admin.headers["content-type"]
    assert "Operator" in res_admin.text

    for retired_path in ("/admin", "/nathan-eh-foda"):
        assert unauth_client.get(retired_path).status_code == 404

    # The operator console's HTML/JS/CSS must never be reachable through the
    # public /frontend static mount (Spec 08 §3.1) — only through the
    # dedicated authenticated /operator routes backed by the separate
    # operator/ directory.
    for path in ("/frontend/admin.html", "/frontend/admin.js", "/frontend/admin.css"):
        assert unauth_client.get(path).status_code == 404, f"{path} must not exist on the /frontend static mount"

