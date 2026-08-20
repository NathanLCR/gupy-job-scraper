"""
SkillPulse AI - Multi-Source Public Job Ingestion Suite.
Tests adapters, normalization, fingerprint deduplication, deterministic ID generation,
and the IngestionManager orchestrator.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, init_db
from entities import JobPost, Job, Company
from services.ingestion.base_adapter import BaseIngestionAdapter
from services.ingestion.arbeitnow_adapter import ArbeitnowAdapter
from services.ingestion.remotive_adapter import RemotiveAdapter
from services.ingestion.jobicy_adapter import JobicyAdapter
from services.ingestion.himalayas_adapter import HimalayasAdapter
from services.ingestion.remoteok_adapter import RemoteOKAdapter
from services.ingestion.gupy_adapter import GupyAdapter
from services.ingestion.ingestion_manager import IngestionManager, ingestion_manager


client = TestClient(app)


# ==============================================================================
# 1. BASE ADAPTER UTILITIES TESTS
# ==============================================================================

def test_clean_html_strips_tags_and_decodes_entities():
    raw_html = "<p>We are hiring a <strong>Senior Python Developer</strong> &amp; Cloud Architect.</p><br><li>AWS &nbsp; experience required</li>"
    cleaned = BaseIngestionAdapter.clean_html(raw_html)
    assert "We are hiring a Senior Python Developer & Cloud Architect." in cleaned
    assert "AWS experience required" in cleaned
    assert "<p>" not in cleaned
    assert "<strong>" not in cleaned


def test_generate_fingerprint_deterministic_and_case_insensitive():
    fp1 = BaseIngestionAdapter.generate_fingerprint("Acme Corp", "Senior Python Engineer", "Berlin, Germany")
    fp2 = BaseIngestionAdapter.generate_fingerprint("  acme corp  ", "senior python engineer", "berlin, germany")
    fp3 = BaseIngestionAdapter.generate_fingerprint("Different Corp", "Senior Python Engineer", "Berlin, Germany")
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 64  # SHA-256 hex


def test_generate_job_id_preserves_gupy_integers():
    gupy_id = BaseIngestionAdapter.generate_job_id("gupy", 1234567, "some_fp")
    assert gupy_id == 1234567

    gupy_str_id = BaseIngestionAdapter.generate_job_id("gupy", "9876543", "some_fp")
    assert gupy_str_id == 9876543


def test_generate_job_id_hashes_alphanumeric_slugs_to_positive_63bit_int():
    slug_id = BaseIngestionAdapter.generate_job_id("arbeitnow", "senior-backend-engineer-sumup-12345")
    assert isinstance(slug_id, int)
    assert 0 < slug_id <= 0x7FFFFFFFFFFFFFFF

    # Determinism
    slug_id2 = BaseIngestionAdapter.generate_job_id("arbeitnow", "senior-backend-engineer-sumup-12345")
    assert slug_id == slug_id2


# ==============================================================================
# 2. ADAPTER NORMALIZATION TESTS
# ==============================================================================

def test_arbeitnow_adapter_normalization():
    adapter = ArbeitnowAdapter()
    sample = {
        "slug": "senior-python-dev-berlin-123",
        "company_name": "TechCo Berlin",
        "title": "Senior Python Developer",
        "description": "<p>Looking for a Python &amp; FastAPI expert in Berlin.</p>",
        "remote": True,
        "url": "https://arbeitnow.com/jobs/senior-python-dev-berlin-123",
        "tags": ["Python", "FastAPI", "Docker", "PostgreSQL"],
        "job_types": ["Full Time"],
        "location": "Berlin, Germany",
        "created_at": 1713500000,
    }

    norm = adapter.normalize_job(sample)
    assert norm["source"] == "arbeitnow"
    assert norm["name"] == "Senior Python Developer"
    assert norm["career_page_name"] == "TechCo Berlin"
    assert norm["region"] == "Europe"
    assert norm["country_code"] == "DE"
    assert norm["currency"] == "EUR"
    assert norm["is_remote_work"] is True
    assert norm["workplace_type"] == "REMOTE"
    assert "FastAPI" in norm["skills"]
    assert "Looking for a Python & FastAPI expert in Berlin." in norm["description"]


def test_remotive_adapter_normalization():
    adapter = RemotiveAdapter()
    sample = {
        "id": 889911,
        "url": "https://remotive.com/job/889911",
        "title": "Staff Backend Engineer",
        "company_name": "CloudScale Inc",
        "company_logo": "https://remotive.com/logo.png",
        "category": "Software Development",
        "tags": ["golang", "kubernetes", "aws"],
        "job_type": "full_time",
        "publication_date": "2026-08-19T10:00:00",
        "candidate_required_location": "USA Only",
        "salary": "$150k - $180k",
        "description": "<div>Build resilient Go microservices on AWS.</div>",
    }

    norm = adapter.normalize_job(sample)
    assert norm["source"] == "remotive"
    assert norm["name"] == "Staff Backend Engineer"
    assert norm["region"] == "North America"
    assert norm["country_code"] == "US"
    assert norm["currency"] == "USD"
    assert norm["is_remote_work"] is True
    assert "golang" in norm["skills"]
    assert "Build resilient Go microservices on AWS." in norm["description"]


def test_jobicy_adapter_normalization():
    adapter = JobicyAdapter()
    sample = {
        "id": 445566,
        "url": "https://jobicy.com/jobs/445566",
        "jobTitle": "Lead Data Scientist",
        "companyName": "DataWise Corp",
        "companyLogo": "https://jobicy.com/logo.png",
        "jobIndustry": ["Data Science", "AI / ML"],
        "jobType": ["full-time"],
        "jobGeo": "Worldwide",
        "jobLevel": "Lead",
        "jobDescription": "<p>Lead machine learning modeling with PyTorch &amp; HuggingFace.</p>",
        "pubDate": "2026-08-18 14:00:00",
        "salaryMin": 130000,
        "salaryMax": 160000,
        "salaryCurrency": "USD",
    }

    norm = adapter.normalize_job(sample)
    assert norm["source"] == "jobicy"
    assert norm["name"] == "Lead Data Scientist"
    assert norm["region"] == "Global"
    assert norm["currency"] == "USD"
    assert "Data Science" in norm["skills"]
    assert "Lead machine learning modeling with PyTorch & HuggingFace." in norm["description"]


def test_himalayas_adapter_normalization():
    adapter = HimalayasAdapter()
    sample = {
        "guid": "himalayas-guid-7788",
        "title": "Senior DevOps Engineer",
        "companyName": "InfraStack Ltd",
        "companyLogo": "https://himalayas.app/logo.png",
        "employmentType": "Full-time",
        "minSalary": 120000,
        "maxSalary": 150000,
        "currency": "USD",
        "seniority": ["Senior"],
        "categories": ["DevOps", "Terraform", "CI/CD"],
        "description": "<p>Manage multi-region Kubernetes clusters with Terraform.</p>",
        "pubDate": "2026-08-18T12:00:00Z",
        "applicationLink": "https://himalayas.app/jobs/7788",
    }

    norm = adapter.normalize_job(sample)
    assert norm["source"] == "himalayas"
    assert norm["name"] == "Senior DevOps Engineer"
    assert "Terraform" in norm["skills"]
    assert norm["is_remote_work"] is True


def test_remoteok_adapter_normalization():
    adapter = RemoteOKAdapter()
    sample = {
        "id": "100200",
        "slug": "remoteok-fullstack-dev-100200",
        "position": "Fullstack React & Node Developer",
        "company": "NextGen Apps",
        "tags": ["react", "node", "typescript"],
        "description": "<p>Modern React 19 and Node.js fullstack development.</p>",
        "location": "Worldwide",
        "apply_url": "https://remoteok.com/apply/100200",
        "salary_min": 90000,
        "salary_max": 120000,
        "date": "2026-08-19",
    }

    norm = adapter.normalize_job(sample)
    assert norm["source"] == "remoteok"
    assert norm["name"] == "Fullstack React & Node Developer"
    assert "react" in norm["skills"]
    assert norm["region"] == "Global"


# ==============================================================================
# 3. INGESTION MANAGER ORCHESTRATION TESTS
# ==============================================================================

def test_ingestion_manager_available_sources():
    sources = ingestion_manager.get_available_sources()
    source_ids = [s["id"] for s in sources]
    assert "arbeitnow" in source_ids
    assert "remotive" in source_ids
    assert "jobicy" in source_ids
    assert "himalayas" in source_ids
    assert "remoteok" in source_ids
    assert "gupy" in source_ids


def test_ingestion_manager_deduplication_and_ingestion():
    mgr = IngestionManager()

    mock_adapter = MagicMock(spec=BaseIngestionAdapter)
    mock_adapter.source_name = "test_feed"
    mock_adapter.display_name = "Test Feed"
    mock_adapter.description = "Test Feed Description"
    mock_adapter.default_region = "Europe"
    mock_adapter.default_country = "IE"
    mock_adapter.default_currency = "EUR"
    mock_adapter.endpoint_url = "https://test.local/api"
    mock_adapter.supports_search_terms = True

    # Return 2 mock jobs with distinct fingerprints
    mock_jobs = [
        {
            "id": 999111,
            "source": "test_feed",
            "name": "Cloud Security Specialist",
            "career_page_name": "CyberSec Global",
            "description": "Secure AWS cloud infrastructure.",
            "is_remote_work": True,
            "workplace_type": "REMOTE",
            "region": "Europe",
            "country_code": "IE",
            "currency": "EUR",
            "fingerprint": "mock_fp_001",
        },
        {
            "id": 999222,
            "source": "test_feed",
            "name": "Rust Systems Developer",
            "career_page_name": "RustCore Lab",
            "description": "Low-latency systems engineering with Rust.",
            "is_remote_work": True,
            "workplace_type": "REMOTE",
            "region": "Europe",
            "country_code": "DE",
            "currency": "EUR",
            "fingerprint": "mock_fp_002",
        },
    ]
    mock_adapter.scrape.return_value = mock_jobs

    mgr._adapters = {"test_feed": mock_adapter}

    # First ingestion run: both should be inserted
    res1 = mgr.ingest(source="test_feed", auto_extract=False)
    assert res1["status"] == "completed"
    assert res1["total_inserted"] == 2
    assert res1["total_skipped"] == 0

    # Second ingestion run with same jobs: both should be skipped (deduplication)
    res2 = mgr.ingest(source="test_feed", auto_extract=False)
    assert res2["status"] == "completed"
    assert res2["total_inserted"] == 0
    assert res2["total_skipped"] == 2


# ==============================================================================
# 4. REST API ENDPOINT TESTS
# ==============================================================================

def test_api_get_ingest_sources():
    resp = client.get("/api/v1/jobs/ingest/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    source_names = [s["id"] for s in data["sources"]]
    assert "arbeitnow" in source_names
    assert "remotive" in source_names
    assert "gupy" in source_names


def test_api_get_ingest_status():
    resp = client.get("/api/v1/jobs/ingest/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "sources_stats" in data


def test_api_post_ingest_triggers_task():
    resp = client.post(
        "/api/v1/jobs/ingest",
        json={"source": "arbeitnow", "limit": 10, "auto_extract": False},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "PENDING"
    assert data["result"]["source"] == "arbeitnow"


def test_api_list_jobs_filter_by_source():
    resp = client.get("/api/v1/jobs?source=gupy&page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    for item in data["items"]:
        assert item["source"] == "gupy"
