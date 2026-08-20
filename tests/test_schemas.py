import pytest
from pydantic import ValidationError
from schemas import (
    CandidateMatchRequest,
    CandidateProfileCreate,
    ExtractionRequest,
    HealthResponse,
    JobFilterParams,
    JobIngestRequest,
    SearchTermCreate,
)


def test_health_response_schema():
    res = HealthResponse(status="ok", version="1.0.0")
    assert res.status == "ok"
    assert res.database == "connected"


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
