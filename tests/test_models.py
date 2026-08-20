import pytest
from entities import (
    CandidateProfile,
    City,
    Company,
    ContractType,
    HardSkill,
    Job,
    JobPost,
    NiceToHaveSkill,
    SearchTerm,
    SkillAlias,
    SkillCooccurrence,
    SoftSkill,
    State,
    TaxonomyNode,
)


def test_job_model_multi_region():
    job = Job(
        id=1,
        job_title="Senior Python Engineer",
        extractor_type="regex",
        salary=15000,
        seniority="Senior",
        years_experience=5,
        tech_stack=["Python", "FastAPI", "PostgreSQL"],
        region="Europe",
        country_code="IE",
        currency="EUR",
        workplace_type="REMOTE",
        fingerprint="sha256_mock_hash_123",
        company_id=10,
    )
    data = job.to_dict()
    assert data["id"] == 1
    assert data["job_title"] == "Senior Python Engineer"
    assert data["region"] == "Europe"
    assert data["country_code"] == "IE"
    assert data["currency"] == "EUR"
    assert data["workplace_type"] == "REMOTE"
    assert data["fingerprint"] == "sha256_mock_hash_123"
    assert "Python" in data["tech_stack"]


def test_candidate_profile_model():
    profile = CandidateProfile(
        id=1,
        name="Nathan Developer",
        email="nathan@example.com",
        raw_resume_text="Experienced in Python, FastAPI, Docker, and Kubernetes.",
        parsed_skills={"hard_skills": ["Python", "FastAPI", "Docker", "Kubernetes"]},
        seniority="Senior",
        target_region="Europe",
        target_role="Backend Engineer",
        years_experience=6,
    )
    data = profile.to_dict()
    assert data["name"] == "Nathan Developer"
    assert data["seniority"] == "Senior"
    assert data["target_region"] == "Europe"
    assert "Python" in data["parsed_skills"]["hard_skills"]


def test_taxonomy_node_model():
    node = TaxonomyNode(
        id=1,
        code="esco:2512.1",
        name="Software Developer",
        type="esco_occupation",
        description="Develops and maintains software applications",
    )
    data = node.to_dict()
    assert data["code"] == "esco:2512.1"
    assert data["type"] == "esco_occupation"


def test_skill_alias_model():
    alias = SkillAlias(
        id=1,
        alias="k8s",
        canonical_name="Kubernetes",
        category="cloud_devops",
        esco_uri="http://data.europa.eu/esco/skill/k8s",
    )
    data = alias.to_dict()
    assert data["alias"] == "k8s"
    assert data["canonical_name"] == "Kubernetes"


def test_skill_cooccurrence_model():
    cooc = SkillCooccurrence(
        id=1,
        skill_a="FastAPI",
        skill_b="Python",
        pair_key="FastAPI::Python",
        cooccurrence_count=42,
        region="Global",
    )
    data = cooc.to_dict()
    assert data["pair_key"] == "FastAPI::Python"
    assert data["cooccurrence_count"] == 42
