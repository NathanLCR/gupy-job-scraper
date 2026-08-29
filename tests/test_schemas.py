import json
import pytest
from pydantic import ValidationError
from schemas import (
    CandidateMatchRequest,
    CandidateProfileCreate,
    ExtractionRequest,
    HealthResponse,
    JobFilterParams,
    JobIngestRequest,
    LivenessResponse,
    ReadinessResponse,
    SearchTermCreate,
)


def test_liveness_response_schema():
    res = LivenessResponse(status="ok", service="SkillPulse", version="1.0.0")
    assert res.status == "ok"
    assert res.service == "SkillPulse"
    assert res.version == "1.0.0"
    data = json.loads(res.model_dump_json())
    assert data == {"status": "ok", "service": "SkillPulse", "version": "1.0.0"}


def test_readiness_response_schema():
    res = ReadinessResponse(
        status="ready",
        database="connected",
        schema_state="current",
        version="1.0.0",
        dependencies={"database": "connected", "redis": "connected"},
    )
    assert res.status == "ready"
    assert res.database == "connected"
    assert res.schema_state == "current"

    # Verify serialization alias produces 'schema' and NOT 'schema_state'
    data = json.loads(res.model_dump_json(by_alias=True))
    assert "schema" in data
    assert "schema_state" not in data
    assert data["schema"] == "current"
    assert "timestamp" not in data
    assert "environment" not in data


def test_extraction_request_schema():
    req = ExtractionRequest(text="We are hiring a Python developer with AWS knowledge.")
    assert req.text.startswith("We are hiring")
    assert req.extractor_type == "regex"


def test_candidate_match_request_schema():
    req = CandidateMatchRequest(
        resume_text="Senior Python and FastAPI developer with 5 years experience in Docker and Postgres.",
        target_region="Europe",
        limit=15,
        min_fit_score=50.0,
    )
    assert req.target_region == "Europe"
    assert req.limit == 15
    assert req.min_fit_score == 50.0


def test_search_term_create_validation():
    # Valid
    st = SearchTermCreate(term="Data Engineer")
    assert st.term == "Data Engineer"
    assert st.is_active is True

    # Empty string should fail
    with pytest.raises(ValidationError):
        SearchTermCreate(term="")


def test_job_ingest_request_defaults():
    req = JobIngestRequest()
    assert req.source == "gupy"
    assert req.limit == 20
    assert req.region == "Latin America"
