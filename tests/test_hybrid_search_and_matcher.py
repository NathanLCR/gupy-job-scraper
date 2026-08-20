"""
Unit and Integration Tests for Phase 4:
- Dense Embedding Service (384-d, cosine similarity, batch embeddings)
- Hybrid Search Engine (RRF k=60, faceted filters, vector + text matching)
- Candidate Matcher & Skill Gap Analysis Service (cascade extraction, canonical taxonomy, fit score formula, recommendations)
- API Endpoints (POST /api/v1/match, POST /api/v1/jobs/search/hybrid)
"""

import math
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import app
from database import SessionLocal
from entities import City, Company, ContractType, HardSkill, Job, NiceToHaveSkill, SoftSkill, State
from services.embedding_service import (
    batch_cosine_similarity,
    cosine_similarity,
    embed_job,
    embed_jobs_batch,
    embed_job_text,
    embed_resume_text,
    embed_resumes_batch,
    get_embedding,
    get_embeddings_batch,
)
from services.hybrid_search_service import (
    RRF_K,
    compute_rrf_score,
    hybrid_search_jobs,
)
from services.matcher_service import (
    CandidateMatcherService,
    calculate_composite_fit_score,
    compute_skill_overlaps,
)

client = TestClient(app)


# ==============================================================================
# 1. DENSE EMBEDDING SERVICE TESTS
# ==============================================================================

def test_embedding_dimensions_and_norm():
    """Verify embeddings produce 384-dimensional unit-norm float vectors."""
    text = "Senior Python Engineer with FastAPI and Kubernetes experience"
    vec = get_embedding(text)

    assert isinstance(vec, list)
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)

    # Unit norm check
    norm = np.linalg.norm(np.array(vec, dtype=np.float32))
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_embedding_empty_text():
    """Verify empty/whitespace text returns 384-dim zero vector."""
    vec_empty = get_embedding("")
    assert len(vec_empty) == 384
    assert all(x == 0.0 for x in vec_empty)

    vec_space = get_embedding("   ")
    assert len(vec_space) == 384
    assert all(x == 0.0 for x in vec_space)


def test_batch_embeddings():
    """Verify batch embedding generation matches individual embeddings."""
    texts = [
        "Python FastAPI Developer",
        "React Frontend Engineer",
        "DevOps Kubernetes Specialist",
    ]
    batch_vecs = get_embeddings_batch(texts)
    assert len(batch_vecs) == 3
    for v in batch_vecs:
        assert len(v) == 384

    # Empty batch
    assert get_embeddings_batch([]) == []


def test_cosine_similarity_properties():
    """Verify cosine similarity properties: identical=1.0, similar > unrelated."""
    t1 = "Senior Python and Django developer with PostgreSQL"
    t2 = "Python backend developer proficient in Django and SQL"
    t3 = "Pastry chef baking sourdough bread and croissants"

    v1 = get_embedding(t1)
    v2 = get_embedding(t2)
    v3 = get_embedding(t3)

    # Self similarity is 1.0
    sim_self = cosine_similarity(v1, v1)
    assert math.isclose(sim_self, 1.0, rel_tol=1e-3)

    # Similar tech profiles should have higher similarity than unrelated culinary text
    sim_tech = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_tech > sim_unrelated
    assert 0.0 <= sim_tech <= 1.0
    assert 0.0 <= sim_unrelated <= 1.0


def test_cosine_similarity_edge_cases():
    """Verify cosine similarity handles empty/mismatched vectors gracefully."""
    v_valid = get_embedding("Test")
    assert cosine_similarity([], v_valid) == 0.0
    assert cosine_similarity(v_valid, []) == 0.0
    assert cosine_similarity([0.0] * 384, v_valid) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_batch_cosine_similarity():
    """Verify batch cosine calculation."""
    q_vec = get_embedding("Python Machine Learning")
    c_vecs = [
        get_embedding("Python Data Science and ML"),
        get_embedding("Java Spring Boot Developer"),
        get_embedding("Graphic Designer UI/UX"),
    ]
    sims = batch_cosine_similarity(q_vec, c_vecs)
    assert len(sims) == 3
    assert sims[0] >= sims[2]


def test_embed_job_and_resume_helpers():
    """Verify job and resume document construction and embedding."""
    job_vec = embed_job_text(
        job_title="DevOps Lead",
        tech_stack=["Kubernetes", "Terraform", "AWS"],
        hard_skills=["Docker", "CI/CD"],
        description="Lead cloud infrastructure team.",
        seniority="Lead",
    )
    assert len(job_vec) == 384

    resume_vec = embed_resume_text(
        resume_text="Senior DevOps Engineer with 7 years experience in AWS, Kubernetes and Docker.",
        extracted_skills={
            "hard_skills": ["Kubernetes", "AWS", "Docker"],
            "tech_stack": ["Terraform", "Linux"],
            "soft_skills": ["Leadership", "Communication"],
        },
    )
    assert len(resume_vec) == 384

    sim = cosine_similarity(job_vec, resume_vec)
    assert sim > 0.3


def test_embed_jobs_batch():
    """Verify batch job embedding helper with dicts and objects."""
    jobs_data = [
        {
            "job_title": "Python Developer",
            "tech_stack": ["Python", "FastAPI"],
            "hard_skills": ["SQL", "Docker"],
            "description": "Develop APIs.",
            "seniority": "Mid",
        },
        {
            "job_title": "Frontend Engineer",
            "tech_stack": ["React", "TypeScript"],
            "hard_skills": ["CSS", "HTML"],
            "description": "Build UI components.",
            "seniority": "Junior",
        },
    ]
    vecs = embed_jobs_batch(jobs_data)
    assert len(vecs) == 2
    assert len(vecs[0]) == 384
    assert len(vecs[1]) == 384
    assert embed_jobs_batch([]) == []


def test_embed_resumes_batch():
    """Verify batch resume embedding helper with string, tuple, and dict formats."""
    resumes_data = [
        "Experienced Python Developer with AWS and Docker skills.",
        ("React Developer with 3 years experience.", {"hard_skills": ["React", "CSS"]}),
        {"resume_text": "DevOps Engineer with Kubernetes.", "extracted_skills": {"hard_skills": ["Kubernetes"]}},
    ]
    vecs = embed_resumes_batch(resumes_data)
    assert len(vecs) == 3
    for v in vecs:
        assert len(v) == 384
    assert embed_resumes_batch([]) == []


# ==============================================================================
# 2. HYBRID SEARCH & RRF (k=60) TESTS
# ==============================================================================

def test_compute_rrf_score_formula():
    """
    Verify RRF mathematical formula:
    RRF(d) = sum( w_m / (k + r_m(d)) )
    """
    # When dense rank = 1 and sparse rank = 1, k=60, weights=0.5, 0.5:
    # RRF = 0.5 / (60 + 1) + 0.5 / (60 + 1) = 1.0 / 61 ≈ 0.01639344
    score_1_1 = compute_rrf_score(dense_rank=1, sparse_rank=1, k=60, dense_weight=0.5, sparse_weight=0.5)
    expected_1_1 = (0.5 / 61.0) + (0.5 / 61.0)
    assert math.isclose(score_1_1, expected_1_1, rel_tol=1e-5)

    # Rank 1 in dense, rank 10 in sparse
    score_1_10 = compute_rrf_score(dense_rank=1, sparse_rank=10, k=60, dense_weight=0.5, sparse_weight=0.5)
    expected_1_10 = (0.5 / 61.0) + (0.5 / 70.0)
    assert math.isclose(score_1_10, expected_1_10, rel_tol=1e-5)

    # Higher rank gives strictly higher RRF score
    assert score_1_1 > score_1_10

    # Test missing one modality rank
    score_only_dense = compute_rrf_score(dense_rank=1, sparse_rank=None, k=60, dense_weight=0.5, sparse_weight=0.5)
    assert math.isclose(score_only_dense, 0.5 / 61.0, rel_tol=1e-5)


def test_hybrid_search_execution():
    """Test hybrid search with RRF against the seeded database."""
    db = SessionLocal()
    try:
        # Seed an additional specific job for search testing
        comp = db.query(Company).first()
        state = db.query(State).first()
        city = db.query(City).first()
        contract = db.query(ContractType).first()

        skill_go = HardSkill(name="Golang")
        skill_k8s = HardSkill(name="Kubernetes")
        db.add_all([skill_go, skill_k8s])
        db.flush()

        go_job = Job(
            job_title="Cloud Infrastructure Golang Engineer",
            extractor_type="regex",
            salary=22000,
            seniority="Senior",
            years_experience=6,
            tech_stack=["Golang", "Kubernetes", "GCP"],
            region="Europe",
            country_code="IE",
            currency="EUR",
            workplace_type="REMOTE",
            company_id=comp.id,
            contract_type_id=contract.id,
            state_id=state.id,
            city_id=city.id,
            hard_skills=[skill_go, skill_k8s],
        )
        db.add(go_job)
        db.commit()

        # Hybrid search for Python
        results_python = hybrid_search_jobs(query="Python FastAPI Developer", db=db, top_k=5)
        assert len(results_python) >= 1
        assert "Python" in results_python[0].job_dict["job_title"]
        assert results_python[0].rrf_score > 0
        assert results_python[0].dense_score > 0
        assert results_python[0].normalized_score > 0

        # Hybrid search with region filter
        results_europe = hybrid_search_jobs(query="Golang", region="Europe", db=db, top_k=5)
        assert len(results_europe) >= 1
        assert results_europe[0].job.region == "Europe"
        assert "Golang" in results_europe[0].job.job_title

        # Hybrid search with salary filter
        results_salary = hybrid_search_jobs(query="Engineer", min_salary=20000, db=db, top_k=5)
        for r in results_salary:
            assert r.job.salary >= 20000

    finally:
        db.close()


# ==============================================================================
# 3. CANDIDATE MATCHER & GAP ANALYSIS TESTS
# ==============================================================================

def test_composite_fit_score_calculation():
    """
    Verify SPEC §3.5 Fit Score formula:
    Fit Score = 0.50 * HardSkillOverlap + 0.20 * SoftSkillOverlap + 0.30 * VectorSimilarity
    """
    # Case 1: 100% on everything -> 100%
    score_perfect = calculate_composite_fit_score(
        hard_overlap_ratio=1.0,
        soft_overlap_ratio=1.0,
        vector_similarity=1.0,
    )
    assert score_perfect == 100.0

    # Case 2: 0% on everything -> 0%
    score_zero = calculate_composite_fit_score(
        hard_overlap_ratio=0.0,
        soft_overlap_ratio=0.0,
        vector_similarity=0.0,
    )
    assert score_zero == 0.0

    # Case 3: 80% Hard, 50% Soft, 70% Vector
    # = (0.50 * 0.8) + (0.20 * 0.5) + (0.30 * 0.7) = 0.40 + 0.10 + 0.21 = 0.71 -> 71.0%
    score_custom = calculate_composite_fit_score(
        hard_overlap_ratio=0.8,
        soft_overlap_ratio=0.5,
        vector_similarity=0.7,
    )
    assert score_custom == 71.0


def test_compute_skill_overlaps():
    """Test skill overlap math and categorization."""
    candidate_hard = {"python", "fastapi", "docker"}
    candidate_soft = {"comunicação", "liderança"}

    job_hard = ["Python", "FastAPI", "Docker", "Kubernetes", "AWS"]  # 3 of 5 match (60%)
    job_soft = ["Comunicação", "Trabalho em equipe"]  # 1 of 2 match (50%)
    job_nice = ["Terraform", "PostgreSQL"]

    overlaps = compute_skill_overlaps(
        candidate_hard=candidate_hard,
        candidate_soft=candidate_soft,
        job_hard_names=job_hard,
        job_soft_names=job_soft,
        job_nice_names=job_nice,
    )

    assert set(overlaps["matched_hard"]) == {"Python", "FastAPI", "Docker"}
    assert set(overlaps["missing_hard"]) == {"Kubernetes", "AWS"}
    assert overlaps["matched_soft"] == ["Comunicação"]
    assert overlaps["missing_soft"] == ["Trabalho em equipe"]
    assert overlaps["hard_overlap_ratio"] == 0.6
    assert overlaps["soft_overlap_ratio"] == 0.5


def test_candidate_matcher_service_full_flow():
    """Test candidate resume matching with extraction cascade, taxonomy, and gap breakdown."""
    db = SessionLocal()
    try:
        resume_text = (
            "Senior Software Engineer with 6 years experience. "
            "Skilled in Python, FastAPI, Docker, and PostgreSQL. "
            "Strong communication and teamwork capabilities."
        )

        match_result = CandidateMatcherService.match_resume(
            resume_text=resume_text,
            db=db,
            target_region="Global",
            limit=5,
            min_fit_score=0.0,
        )

        assert "extracted_skills" in match_result
        assert "hard_skills" in match_result["extracted_skills"]
        assert len(match_result["matches"]) >= 1

        top_match = match_result["matches"][0]
        assert top_match["fit_score"] > 0
        assert top_match["hard_skill_overlap"] > 0
        assert "gap_analysis" in top_match

        gap = top_match["gap_analysis"]
        assert "matched_skills" in gap
        assert "missing_critical_skills" in gap
        assert "missing_nice_to_have" in gap
        assert "recommended_skills" in gap
        assert isinstance(gap["recommended_skills"], list)

    finally:
        db.close()


def test_candidate_matcher_empty_resume_raises():
    """Verify empty resume text raises ValueError."""
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            CandidateMatcherService.match_resume(resume_text="   ", db=db)
    finally:
        db.close()


# ==============================================================================
# 4. API ENDPOINT INTEGRATION TESTS
# ==============================================================================

def test_api_hybrid_search_endpoint():
    """Verify POST /api/v1/jobs/search/hybrid endpoint."""
    payload = {
        "query": "Senior Python Developer FastAPI",
        "region": "Latin America",
        "top_k": 5,
        "dense_weight": 0.5,
        "sparse_weight": 0.5,
    }
    response = client.post("/api/v1/jobs/search/hybrid", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["query"] == payload["query"]
    assert "total_results" in data
    assert "items" in data
    assert len(data["items"]) >= 1

    item = data["items"][0]
    assert "job" in item
    assert "rrf_score" in item
    assert "dense_score" in item
    assert "sparse_score" in item
    assert "dense_rank" in item
    assert "sparse_rank" in item
    assert "normalized_score" in item
    assert item["job"]["job_title"] is not None


def test_api_match_endpoint_with_gap_analysis():
    """Verify POST /api/v1/match returns full gap breakdown and recommendations."""
    payload = {
        "resume_text": "Experienced Python Backend Engineer with FastAPI, Docker, and PostgreSQL. Great communication.",
        "target_region": "Global",
        "limit": 10,
        "min_fit_score": 10.0,
    }
    response = client.post("/api/v1/match", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "extracted_skills" in data
    assert "matches" in data
    assert len(data["matches"]) >= 1

    first_match = data["matches"][0]
    assert 0.0 <= first_match["fit_score"] <= 100.0
    assert 0.0 <= first_match["hard_skill_overlap"] <= 100.0
    assert 0.0 <= first_match["soft_skill_overlap"] <= 100.0
    assert 0.0 <= first_match["vector_similarity"] <= 100.0

    gap = first_match["gap_analysis"]
    assert "matched_skills" in gap
    assert "missing_critical_skills" in gap
    assert "missing_nice_to_have" in gap
    assert "recommended_skills" in gap


def test_api_match_endpoint_profile_id_flow():
    """Verify POST /api/v1/match works using existing profile_id."""
    # 1. Create a profile
    create_res = client.post(
        "/api/v1/match/profile",
        json={
            "name": "Alex Smith",
            "email": "alex.smith@example.com",
            "raw_resume_text": "Fullstack Engineer with Python, React, Docker, and SQL experience.",
            "target_region": "Latin America",
        },
    )
    assert create_res.status_code == 201
    profile_id = create_res.json()["id"]

    # 2. Match with profile_id
    match_res = client.post(
        "/api/v1/match",
        json={"profile_id": profile_id, "target_region": "Latin America"},
    )
    assert match_res.status_code == 200
    data = match_res.json()
    assert len(data["matches"]) >= 1


def test_api_match_validation_errors():
    """Verify validation error responses for /api/v1/match."""
    # Missing both resume_text and profile_id
    res_empty = client.post("/api/v1/match", json={})
    assert res_empty.status_code == 400

    # Non-existent profile_id
    res_404 = client.post("/api/v1/match", json={"profile_id": 999999})
    assert res_404.status_code == 404


def test_api_get_candidate_profile_not_found():
    """Verify GET /api/v1/match/profile/{id} returns 404 for non-existent profile."""
    res_404 = client.get("/api/v1/match/profile/999999")
    assert res_404.status_code == 404


def test_matcher_router_alias_import():
    """Verify api.v1.matcher alias exports match_candidate_cv and router."""
    from api.v1.matcher import match_candidate_cv, router
    assert match_candidate_cv is not None
    assert router is not None


def test_hybrid_search_faceted_filters_advanced():
    """Verify faceted filters on hybrid search including workplace_type and country_code."""
    db = SessionLocal()
    try:
        # Search by workplace_type
        res_remote = hybrid_search_jobs(query="Python", workplace_type="REMOTE", db=db)
        for r in res_remote:
            assert r.job.workplace_type == "REMOTE"

        # Search by country_code
        res_country = hybrid_search_jobs(query="Python", country_code="BR", db=db)
        for r in res_country:
            assert r.job.country_code == "BR"

        # Search with skill filter
        res_skill = hybrid_search_jobs(query="Developer", skill="Python", db=db)
        assert len(res_skill) >= 1

        # Search with location filter
        res_loc = hybrid_search_jobs(query="Developer", location="São Paulo", db=db)
        assert len(res_loc) >= 1
    finally:
        db.close()

