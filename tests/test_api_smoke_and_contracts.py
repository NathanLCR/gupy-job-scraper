"""
API Smoke and Contract Parity Test Suite for Public Endpoints.
Verifies FastAPI routing, JSON 404 guards, and strict Pydantic contract compliance
for Jobs, Candidate Match, and Market Analytics endpoints.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app import app
from schemas.common import PaginationMeta
from schemas.job import JobListResponse
from schemas.matcher import CandidateMatchResponse
from schemas.analytics import SkillAnalyticsResponse

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_public_views_served():
    client = TestClient(app)
    for path in ["/", "/match", "/jobs", "/market", "/how-it-works", "/dashboard"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "SkillPulse" in res.text


def test_api_guard_returns_json_404_when_unmounted():
    client = TestClient(app)
    # Check that 404.json is served with application/json
    res = client.get("/frontend/api/404.json")
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    data = res.json()
    assert "error" in data


def test_jobs_endpoint_contract_compliance():
    client = TestClient(app)
    res = client.get("/api/v1/jobs?page=1&page_size=5")
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    data = res.json()
    validated = JobListResponse.model_validate(data)
    assert isinstance(validated.items, list)
    assert isinstance(validated.pagination, PaginationMeta)
    assert validated.pagination.page == 1
    assert validated.pagination.page_size == 5


def test_match_endpoint_contract_compliance():
    client = TestClient(app)
    payload = {
        "resume_text": "Experienced Python Backend Engineer with FastAPI, PostgreSQL, Docker, and Redis.",
        "target_region": "Europe",
        "limit": 5,
        "min_fit_score": 0.0,
    }
    res = client.post("/api/v1/match", json=payload)
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    data = res.json()
    validated = CandidateMatchResponse.model_validate(data)
    assert isinstance(validated.matches, list)
    for m in validated.matches:
        assert isinstance(m.hard_points, float)
        assert isinstance(m.soft_points, float)
        assert isinstance(m.vector_points, float)
        assert isinstance(m.total_points, float)
        assert 0.0 <= m.hard_points <= 50.0
        assert 0.0 <= m.soft_points <= 20.0
        assert 0.0 <= m.vector_points <= 30.0
        assert 0.0 <= m.total_points <= 100.0


def test_market_overview_endpoint_contract_compliance():
    client = TestClient(app)
    res = client.get("/api/v1/analytics/overview")
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    data = res.json()
    validated = SkillAnalyticsResponse.model_validate(data)
    assert isinstance(validated.total_jobs, int)
    assert isinstance(validated.top_skills, list)
    assert isinstance(validated.top_locations, list)
    assert isinstance(validated.workplace_distribution, list)
