from sqlalchemy import delete

from config import settings
from database import SessionLocal
from entities import Company, Job
from services.embedding_service import EmbeddingResult
from services.embedding_service import EmbeddingUnavailableError
from services.matcher_service import (
    CandidateMatcherService,
    build_candidate_lexical_query,
)
from services.postgres_retrieval_service import RankedCandidate, RetrievalResult


EXTRACTED = {
    "hard_skills": ["Python"],
    "canonical_hard_skills": ["Python"],
    "soft_skills": [],
    "tech_stack": ["Python"],
    "seniority": "Senior",
    "years_experience": 5,
}


def test_candidate_lexical_query_is_stable_and_excludes_duplicate_tech():
    query = build_candidate_lexical_query(
        ["Python", "FastAPI"], ["python", "PostgreSQL"], "Senior"
    )
    assert query == "FastAPI PostgreSQL Python Senior"


def test_missing_embedding_contributes_zero_semantic_points(monkeypatch):
    region = "Matcher Missing Vector Region"
    db = SessionLocal()
    try:
        company = db.query(Company).first()
        job = Job(
            job_title="Python API Engineer",
            extractor_type="regex",
            company_id=company.id,
            region=region,
            embedding=None,
        )
        db.add(job)
        db.commit()

        monkeypatch.setattr(settings, "POSTGRES_INDEXED_RETRIEVAL_ENABLED", False)
        monkeypatch.setattr(
            CandidateMatcherService,
            "parse_and_extract_candidate",
            classmethod(lambda cls, *args, **kwargs: EXTRACTED),
        )
        result = CandidateMatcherService.match_resume(
            "private candidate text", db, target_region=region
        )

        assert result["matches"][0]["vector_points"] == 0.0
        assert result["matches"][0]["vector_similarity"] == 0.0
        assert "Semantic evidence unavailable" in result["matches"][0]["match_reason"]
    finally:
        db.execute(delete(Job).where(Job.region == region))
        db.commit()
        db.close()


def test_match_counts_are_distinct_and_truthful(monkeypatch):
    region = "Matcher Count Contract Region"
    db = SessionLocal()
    try:
        company = db.query(Company).first()
        db.add_all(
            [
                Job(job_title="Python One", extractor_type="regex", company_id=company.id, region=region),
                Job(job_title="Python Two", extractor_type="regex", company_id=company.id, region=region),
            ]
        )
        db.commit()
        monkeypatch.setattr(settings, "POSTGRES_INDEXED_RETRIEVAL_ENABLED", False)
        monkeypatch.setattr(
            CandidateMatcherService,
            "parse_and_extract_candidate",
            classmethod(lambda cls, *args, **kwargs: EXTRACTED),
        )

        result = CandidateMatcherService.match_resume(
            "candidate", db, target_region=region, limit=1, min_fit_score=0
        )

        assert result["total_eligible"] == 2
        assert result["total_evaluated"] == 2
        assert result["total_qualified"] == 2
        assert result["total_matches"] == 1
    finally:
        db.execute(delete(Job).where(Job.region == region))
        db.commit()
        db.close()


def test_indexed_selection_can_return_strongest_job_after_row_200(monkeypatch):
    region = "Matcher Row 201 Region"
    db = SessionLocal()
    try:
        company = db.query(Company).first()
        jobs = [
            Job(
                job_title=f"Role {index:03d}",
                extractor_type="regex",
                company_id=company.id,
                region=region,
                embedding=([0.0] * 383) + [1.0] if index == 200 else None,
                embedding_model="test-model" if index == 200 else None,
            )
            for index in range(201)
        ]
        db.add_all(jobs)
        db.commit()
        strongest_id = jobs[-1].id

        class FakeRepository:
            def __init__(self, db):
                pass

            def retrieve(self, *args, **kwargs):
                return RetrievalResult(
                    (RankedCandidate(strongest_id, 0.02, 1, 1.0, None, None),),
                    "dense",
                )

        monkeypatch.setattr(settings, "POSTGRES_INDEXED_RETRIEVAL_ENABLED", True)
        monkeypatch.setattr(
            CandidateMatcherService,
            "parse_and_extract_candidate",
            classmethod(lambda cls, *args, **kwargs: EXTRACTED),
        )
        monkeypatch.setattr(
            "services.matcher_service.embed_query_checked",
            lambda text: EmbeddingResult(([0.0] * 383) + [1.0], "test-model"),
            raising=False,
        )
        monkeypatch.setattr(
            "services.matcher_service.PostgresRetrievalService", FakeRepository, raising=False
        )

        result = CandidateMatcherService.match_resume(
            "candidate", db, target_region=region, limit=10
        )

        assert result["total_eligible"] == 201
        assert result["total_evaluated"] == 1
        assert result["matches"][0]["job_id"] == strongest_id
    finally:
        db.execute(delete(Job).where(Job.region == region))
        db.commit()
        db.close()


def test_match_api_returns_503_when_embedding_provider_is_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    from app import app

    monkeypatch.setattr(
        CandidateMatcherService,
        "match_resume",
        classmethod(
            lambda cls, *args, **kwargs: (_ for _ in ()).throw(
                EmbeddingUnavailableError("provider secret")
            )
        ),
    )
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/match", json={"resume_text": "python engineer"}
    )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "provider secret" not in response.text
