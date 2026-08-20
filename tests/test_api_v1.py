import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


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
    response = client.post("/api/v1/extract", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Python" in data["hard_skills"]
    assert "FastAPI" in data["hard_skills"]
    assert "Docker" in data["hard_skills"]
    assert "Kubernetes" in data["nice_to_have"]
    assert data["seniority"] == "Sênior"
    assert data["years_experience"] == 5


def test_extract_empty_text():
    response = client.post("/api/v1/extract", json={"text": "   "})
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
    response = client.post("/api/v1/match/profile", json=payload)
    assert response.status_code == 201
    profile = response.json()
    assert profile["id"] is not None
    assert profile["name"] == "Jane Doe"
    assert profile["seniority"] == "Lead"

    # Fetch created profile
    get_res = client.get(f"/api/v1/match/profile/{profile['id']}")
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
    # 1. Unauthenticated request to protected endpoint should fail with 401
    unauth_res = client.get("/api/v1/errors")
    assert unauth_res.status_code == 401

    # 2. Invalid credentials should fail with 401
    login_fail = client.post("/api/v1/admin/login", json={"key": "wrong-key"})
    assert login_fail.status_code == 401

    # 3. Valid login should return token
    login_ok = client.post("/api/v1/admin/login", json={"key": "skillpulse-admin-secret"})
    assert login_ok.status_code == 200
    assert login_ok.json()["status"] == "ok"
    assert "token" in login_ok.json()

    # 4. Authenticated request with header should succeed
    auth_headers = {"X-Admin-Key": "skillpulse-admin-secret"}
    verify_res = client.get("/api/v1/admin/verify", headers=auth_headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "authenticated"


def test_search_terms_crud():
    headers = {"X-Admin-Key": "skillpulse-admin-secret"}
    # 1. Create a search term (requires admin auth)
    term_payload = {"term": "Rust Developer", "is_active": True}
    res = client.post("/api/v1/search-terms", json=term_payload, headers=headers)
    assert res.status_code in [201, 400]  # 400 if already exists in test DB

    # 2. List search terms
    list_res = client.get("/api/v1/search-terms?page=1&page_size=20", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()["items"]) > 0


def test_stats_and_errors_endpoints():
    stats_res = client.get("/api/v1/stats")
    assert stats_res.status_code == 200
    assert "jobs_count" in stats_res.json()

    headers = {"X-Admin-Key": "skillpulse-admin-secret"}
    errors_res = client.get("/api/v1/errors", headers=headers)
    assert errors_res.status_code == 200
    assert "items" in errors_res.json()


def test_frontend_routes():
    # Public candidate dashboard
    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    assert "text/html" in res_dash.headers["content-type"]
    assert "SkillPulse" in res_dash.text
    assert "Candidate Match" in res_dash.text

    # Protected operator console
    res_admin = client.get("/admin")
    assert res_admin.status_code == 200
    assert "text/html" in res_admin.headers["content-type"]
    assert "Operator" in res_admin.text


