import pytest
from database import SessionLocal
from entities import Job, JobPost, HardSkill, Company
from services.error_service import log_error, get_errors
from services.features_service_hm import (
    get_technology_trends,
    get_top_locations,
    get_jobs_by_contract_type,
    get_jobs_by_seniority,
)
from services.matcher_service import compute_skill_overlaps
from services.embedding_service import embed_candidate, embed_job


def test_job_64bit_biginteger_id():
    """Verify that Job and JobPost handle 64-bit integer IDs without overflow."""
    large_64bit_id = 7891234567890123456
    db = SessionLocal()
    try:
        comp = Company(name="Large Corp Enterprise")
        db.add(comp)
        db.flush()

        post = JobPost(
            id=large_64bit_id,
            company_id=comp.id,
            name="Principal Architect",
            description="Leading microservices with Python, Go, and Kafka.",
            region="Europe",
            country_code="DE",
            currency="EUR",
        )
        job = Job(
            id=large_64bit_id,
            company_id=comp.id,
            job_title="Principal Architect",
            extractor_type="cascade",
            region="Europe",
            country_code="DE",
            currency="EUR",
            tech_stack=["Python", "Go", "Kafka"],
        )
        db.add(post)
        db.add(job)
        db.commit()

        fetched_job = db.get(Job, large_64bit_id)
        assert fetched_job is not None
        assert fetched_job.id == large_64bit_id
        assert fetched_job.to_dict()["id"] == large_64bit_id
    finally:
        db.rollback()
        db.close()


def test_error_logging_with_unserializable_objects():
    """Verify log_error serializes non-standard objects without throwing TypeError."""
    class CustomObj:
        def __repr__(self):
            return "<CustomUnserializableObject>"

    # Should not raise exception
    log_error(
        message="Test unserializable error logging",
        source="test.unserializable",
        payload={"obj": CustomObj(), "exc": ValueError("sample error")},
    )

    errors = get_errors(source="test.unserializable")
    assert len(errors) > 0
    assert "Test unserializable" in errors[0]["message"]
    assert "<CustomUnserializableObject>" in (errors[0]["payload"] or "")


def test_technology_trends_ilike_and_region():
    """Verify get_technology_trends supports case-insensitive partial searches and region filtering."""
    res_partial = get_technology_trends(days=30, limit=5, skill="pyth")
    assert "series" in res_partial
    assert res_partial["selected_skill"] == "pyth"

    res_region = get_technology_trends(days=30, limit=5, region="Europe")
    assert "series" in res_region


def test_skill_overlaps_zero_bias_for_empty_jobs():
    """Verify compute_skill_overlaps returns 0.0 overlap for empty job requirements instead of artificial 50%/80%."""
    candidate_hard = {"python", "fastapi"}
    candidate_soft = {"leadership"}

    # Job with empty requirements
    overlaps = compute_skill_overlaps(
        candidate_hard=candidate_hard,
        candidate_soft=candidate_soft,
        job_hard_names=[],
        job_soft_names=[],
    )
    assert overlaps["hard_overlap_ratio"] == 0.0
    assert overlaps["soft_overlap_ratio"] == 0.0

    # Job with matching requirements
    overlaps_match = compute_skill_overlaps(
        candidate_hard=candidate_hard,
        candidate_soft=candidate_soft,
        job_hard_names=["Python", "Docker"],
        job_soft_names=["Leadership"],
    )
    assert overlaps_match["hard_overlap_ratio"] == 0.5
    assert overlaps_match["soft_overlap_ratio"] == 1.0


def test_analytics_sub_endpoints_with_region():
    """Verify auxiliary analytics helpers accept and filter by region safely."""
    locs = get_top_locations(n=5, region="Europe")
    assert isinstance(locs, list)

    contracts = get_jobs_by_contract_type(region="Europe")
    assert isinstance(contracts, list)

    seniorities = get_jobs_by_seniority(region="Latin America")
    assert isinstance(seniorities, list)


def test_embed_candidate_helper():
    """Verify embed_candidate handles dictionaries and entity-like objects."""
    extracted = {
        "raw_resume_text": "Experienced Python Engineer building REST APIs with FastAPI.",
        "hard_skills": ["Python", "FastAPI"],
        "soft_skills": ["Problem Solving"],
    }
    vec = embed_candidate(extracted)
    assert isinstance(vec, list)
    assert len(vec) == 384
