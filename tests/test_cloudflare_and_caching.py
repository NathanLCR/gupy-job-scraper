"""
Unit & Integration Tests for Cloudflare-First Architecture:
1. Cloudflare Workers AI BGE-small embedding cascade (384 dimensions).
2. LLMExtractionService SHA-256 caching and failover cascade.
3. Candidate resume free-text parsing and /match/explain endpoint.
4. IP-based public rate limiting.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app import app
from config import settings
from entities import Base, Company, HardSkill, Job, JobPost, SoftSkill
from features_extractors.llm_extractor import (
    LLMExtractionService,
    compute_extraction_fingerprint,
    extract as llm_extract,
    get_cached_extraction,
    store_cached_extraction,
)
from services.embedding_service import (
    EMBEDDING_DIM,
    _call_cloudflare_workers_ai,
    get_embedding,
    get_embeddings_batch,
)
from services.matcher_service import CandidateMatcherService

client = TestClient(app)


def operator_headers():
    settings.ADMIN_API_KEY = "test-operator-secret-cloudflare-tests-32"
    return {"Authorization": "Bearer test-operator-secret-cloudflare-tests-32"}


# ==============================================================================
# 1. EMBEDDINGS & CLOUDFLARE WORKERS AI TESTS
# ==============================================================================

class TestCloudflareEmbeddings:

    def test_workers_ai_embedding_mock_success(self):
        fake_vector = [0.05] * EMBEDDING_DIM
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"shape": [1, 384], "data": [fake_vector]},
            "success": True,
        }

        with patch("config.settings.CF_ACCOUNT_ID", "test_acc"), \
             patch("config.settings.CF_API_TOKEN", "test_tok"), \
             patch("requests.post", return_value=mock_response):
            vectors = _call_cloudflare_workers_ai("Software Engineer Python FastAPI")
            assert vectors is not None
            assert len(vectors) == 1
            assert len(vectors[0]) == EMBEDDING_DIM

    def test_embedding_fallback_to_deterministic_is_384d(self):
        with patch("config.settings.CF_ACCOUNT_ID", None), \
             patch("services.embedding_service._load_transformer_model", return_value=None):
            emb = get_embedding("Senior Backend Engineer Kubernetes")
            assert isinstance(emb, list)
            assert len(emb) == EMBEDDING_DIM

            batch = get_embeddings_batch(["Python Developer", "React Frontend"])
            assert len(batch) == 2
            assert len(batch[0]) == EMBEDDING_DIM
            assert len(batch[1]) == EMBEDDING_DIM


# ==============================================================================
# 2. SHA-256 EXTRACTION CACHING & ROUTER FAILOVER TESTS
# ==============================================================================

class TestLLMExtractionServiceAndCaching:

    def test_fingerprint_deterministic_and_case_insensitive(self):
        fp1 = compute_extraction_fingerprint("  Senior Python Engineer with AWS  ", prompt_version="v1.0")
        fp2 = compute_extraction_fingerprint("senior python engineer with aws", prompt_version="v1.0")
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_caching_prevents_duplicate_llm_calls(self):
        sample_text = "Job posting requiring Go, Kubernetes and Docker in São Paulo"
        fp = compute_extraction_fingerprint(sample_text, prompt_version="v1.0", schema_type="job")

        fake_extracted = {
            "job_title": "Go Developer",
            "hard_skills": ["Go", "Kubernetes", "Docker"],
            "soft_skills": ["Teamwork"],
            "tech_stack": ["Backend"],
            "confidence_score": 0.95,
        }
        store_cached_extraction(fp, fake_extracted)

        # Call extract_job with patch to ensure requests.post is NEVER called
        with patch("requests.post") as mock_post:
            result = LLMExtractionService.extract_job(sample_text)
            assert not mock_post.called
            assert result["job_title"] == "Go Developer"
            assert "Go" in result["hard_skills"]
            assert result["tier_used"] == "cached_llm"

    def test_groq_failover_to_openrouter_on_429(self):
        groq_429_resp = MagicMock()
        groq_429_resp.status_code = 429
        groq_429_resp.headers = {"retry-after": "0"}

        openrouter_200_resp = MagicMock()
        openrouter_200_resp.status_code = 200
        openrouter_200_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"job_title": "Rust Systems Engineer", "hard_skills": ["Rust", "Linux"]}'
                }
            }]
        }

        def fake_post(url, **kwargs):
            if "groq.com" in url:
                import requests
                raise requests.exceptions.HTTPError("429 Too Many Requests", response=groq_429_resp)
            elif "openrouter.ai" in url:
                return openrouter_200_resp
            return MagicMock(status_code=500)

        with patch("config.settings.GROQ_API_KEY", "mock_groq_key"), \
             patch("config.settings.OPENROUTER_API_KEY", "mock_or_key"), \
             patch("requests.post", side_effect=fake_post), \
             patch("time.sleep"):  # fast test
            result = LLMExtractionService.extract_job("Unique Rust Job Text 12345")
            assert result["job_title"] == "Rust Systems Engineer"
            assert "Rust" in result["hard_skills"]
            assert result["tier_used"] == "tier3_cloud_llm_openrouter"


# ==============================================================================
# 3. CANDIDATE RESUME PARSING & /MATCH/EXPLAIN TESTS
# ==============================================================================

class TestCandidateExplanationAndParsing:

    def test_candidate_resume_free_text_parser(self):
        resume = "4 years of experience as Backend Engineer with Python, FastAPI, PostgreSQL and Docker."
        fake_profile_data = {
            "job_title": "Backend Engineer",
            "seniority": "Pleno",
            "years_experience": 4,
            "hard_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "soft_skills": ["Communication"],
            "tech_stack": ["Backend"],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": str(fake_profile_data).replace("'", '"')}}]
        }

        with patch("config.settings.GROQ_API_KEY", "mock_key"), \
             patch("requests.post", return_value=mock_resp):
            profile = LLMExtractionService.parse_candidate_profile(resume)
            assert profile["job_title"] == "Backend Engineer"
            assert profile["years_experience"] == 4
            assert "Python" in profile["hard_skills"]

    def test_explain_candidate_match_endpoint(self, monkeypatch):
        # Fetch an existing seeded job or create a isolated test job
        from database import SessionLocal
        db = SessionLocal()
        created_temp = False
        try:
            job = db.query(Job).first()
            if not job:
                created_temp = True
                company = Company(name="Cloudflare Edge Tech")
                db.add(company)
                db.flush()

                job = Job(
                    company_id=company.id,
                    job_title="Senior Python Cloud Engineer",
                    workplace_type="REMOTE",
                    salary=15000,
                    currency="BRL",
                )
                db.add(job)
                db.commit()
                db.refresh(job)

            job_id = job.id
            expected_title = job.job_title
        finally:
            db.close()

        payload = {
            "resume_text": "Experienced Python and FastAPI developer with 5 years building scalable APIs.",
            "job_id": job_id,
        }

        try:
            response = client.post(
                "/api/v1/match/explain", json=payload, headers=operator_headers()
            )
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == job_id
            assert data["job_title"] == expected_title
            assert "fit_score" in data
            assert "hard_skill_overlap" in data
            assert "explanation" in data
            assert isinstance(data["explanation"], str)
            assert len(data["explanation"]) > 10
        finally:
            if created_temp:
                cleanup_db = SessionLocal()
                try:
                    j = cleanup_db.get(Job, job_id)
                    if j:
                        cleanup_db.delete(j)
                    cleanup_db.commit()
                except Exception:
                    cleanup_db.rollback()
                finally:
                    cleanup_db.close()


# ==============================================================================
# 4. PUBLIC API RATE LIMITING TEST
# ==============================================================================

class TestPublicRateLimiting:

    def test_rate_limit_exceeded_returns_429(self):
        from services.rate_limit_service import RateLimitDecision
        mock_limiter = MagicMock()
        mock_limiter.check.side_effect = [
            RateLimitDecision(allowed=True, limit=2, remaining=1, retry_after_seconds=0, reset_after_seconds=60),
            RateLimitDecision(allowed=True, limit=2, remaining=0, retry_after_seconds=0, reset_after_seconds=60),
            RateLimitDecision(allowed=False, limit=2, remaining=0, retry_after_seconds=42, reset_after_seconds=60),
        ]
        with patch("config.settings.RATE_LIMIT_ENABLED", True), \
             patch("config.settings.RATE_LIMIT_EXTRACT_RPM", 2), \
             patch("app.get_rate_limiter", return_value=mock_limiter):
            payload = {"text": "Simple test payload for rate limiter"}
            headers = operator_headers()
            # Request 1: OK
            r1 = client.post("/api/v1/extract", json=payload, headers=headers)
            assert r1.status_code in (200, 429)

            # Request 2: OK
            r2 = client.post("/api/v1/extract", json=payload, headers=headers)

            # Request 3: 429 Too Many Requests
            r3 = client.post("/api/v1/extract", json=payload, headers=headers)
            assert r3.status_code == 429
            assert "Retry-After" in r3.headers
            assert "Rate limit exceeded" in r3.json()["detail"]
