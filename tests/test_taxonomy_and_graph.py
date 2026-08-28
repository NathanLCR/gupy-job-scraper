"""
Unit and integration tests for Phase 3:
Canonical Taxonomy (ESCO / O*NET) & Co-occurrence Graph Engine.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import app
from config import settings
from database import SessionLocal
from entities import Company, HardSkill, Job, SkillAlias, SkillCooccurrence, TaxonomyNode
from services.cooccurrence_service import (
    compute_cooccurrence_graph,
    compute_metrics,
    sync_cooccurrences_to_db,
)
from services.taxonomy_service import (
    get_canonical_alias_map,
    get_taxonomy_tree,
    normalize_skill,
    normalize_skills,
    seed_default_taxonomy,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------
# Taxonomy & Skill Alias Tests
# ---------------------------------------------------------

def test_seed_default_taxonomy(db_session):
    """Verify taxonomy and aliases are seeded idempotently."""
    res = seed_default_taxonomy(db_session)
    assert isinstance(res, dict)
    assert "nodes_created" in res
    assert "aliases_created" in res

    # Check that root taxonomy nodes exist
    nodes = db_session.scalars(select(TaxonomyNode)).all()
    assert len(nodes) >= 7

    # Check that skill aliases exist
    aliases = db_session.scalars(select(SkillAlias)).all()
    assert len(aliases) >= 50


def test_normalize_skill_aliases(db_session):
    """Verify raw skill aliases resolve to canonical ESCO/O*NET entities."""
    # Kubernetes variants
    for variant in ["k8s", "kubernetes", "kube", "k8s cluster"]:
        norm = normalize_skill(variant, db=db_session)
        assert norm.canonical_name == "Kubernetes"
        assert norm.category == "Cloud & DevOps"
        assert norm.esco_uri == "http://data.europa.eu/esco/skill/kubernetes"
        assert norm.onet_code == "15-1251.00"

    # PostgreSQL variants
    for variant in ["postgres", "postgresql", "pgsql"]:
        norm = normalize_skill(variant, db=db_session)
        assert norm.canonical_name == "PostgreSQL"
        assert norm.category == "Databases & Storage"

    # React variants
    for variant in ["react", "reactjs", "react.js"]:
        norm = normalize_skill(variant, db=db_session)
        assert norm.canonical_name == "React"
        assert norm.category == "Frontend & Web"

    # FastAPI variants
    for variant in ["fastapi", "fast api"]:
        norm = normalize_skill(variant, db=db_session)
        assert norm.canonical_name == "FastAPI"
        assert norm.category == "Backend & APIs"

    # AI / ML variants
    norm_ml = normalize_skill("ml", db=db_session)
    assert norm_ml.canonical_name == "Machine Learning"
    assert norm_ml.category == "Data & AI"

    norm_llm = normalize_skill("genai", db=db_session)
    assert norm_llm.canonical_name == "Large Language Models"
    assert norm_llm.category == "Data & AI"


def test_normalize_skills_batch(db_session):
    """Verify batch normalization and deduplication of skills."""
    raw_list = ["k8s", "Kubernetes", "kube", "python", "py", "fastapi"]
    results = normalize_skills(raw_list, db=db_session)

    canonical_names = [item.canonical_name for item in results]
    assert canonical_names == ["Kubernetes", "Python", "FastAPI"]
    assert len(results) == 3


def test_normalize_unknown_skill(db_session):
    """Verify fallback normalization for non-aliased skill terms."""
    norm = normalize_skill("custom-framework-xyz", db=db_session)
    assert norm.canonical_name == "Custom-Framework-Xyz"
    assert norm.category == "technical"
    assert norm.esco_uri is None


def test_get_taxonomy_tree(db_session):
    """Verify recursive taxonomy tree building."""
    tree = get_taxonomy_tree(db_session)
    assert len(tree) >= 7

    # Ensure backend category has children
    backend_node = next((n for n in tree if n.code == "CAT-BACKEND"), None)
    assert backend_node is not None
    assert len(backend_node.children) >= 2


def test_get_canonical_alias_map(db_session):
    """Verify canonical alias map returns dictionary mapping."""
    alias_map = get_canonical_alias_map(db_session)
    assert "k8s" in alias_map
    assert alias_map["k8s"]["canonical_name"] == "Kubernetes"
    assert "reactjs" in alias_map
    assert alias_map["reactjs"]["canonical_name"] == "React"


# ---------------------------------------------------------
# Co-occurrence & Graph Metrics Tests
# ---------------------------------------------------------

def test_compute_metrics_math():
    """Verify Support and Lift calculations."""
    # N=10, c(A)=5, c(B)=4, c(A, B)=2
    # Support = 2/10 = 0.20
    # Lift = (2 * 10) / (5 * 4) = 20 / 20 = 1.0
    support, lift = compute_metrics(count_ab=2, count_a=5, count_b=4, total_jobs=10)
    assert support == 0.20
    assert lift == 1.0

    # Strong association: N=10, c(A)=2, c(B)=2, c(A, B)=2
    # Support = 2/10 = 0.20
    # Lift = (2 * 10) / (2 * 2) = 20 / 4 = 5.0
    support2, lift2 = compute_metrics(count_ab=2, count_a=2, count_b=2, total_jobs=10)
    assert support2 == 0.20
    assert lift2 == 5.0

    # Edge cases
    assert compute_metrics(0, 0, 0, 0) == (0.0, 0.0)


def test_compute_cooccurrence_graph(db_session):
    """Verify graph generation with nodes, edges, lift, and clusters."""
    comp = db_session.scalar(select(Company))
    if not comp:
        comp = Company(name="Test Corp")
        db_session.add(comp)
        db_session.flush()

    # Seed extra jobs for graph testing
    job2 = Job(
        job_title="Cloud DevOps Engineer",
        extractor_type="regex",
        salary=22000,
        tech_stack=["Docker", "Kubernetes", "AWS", "Python"],
        region="Latin America",
        company_id=comp.id,
    )
    job3 = Job(
        job_title="Full Stack Engineer",
        extractor_type="regex",
        salary=16000,
        tech_stack=["Python", "FastAPI", "React", "Docker"],
        region="Latin America",
        company_id=comp.id,
    )
    db_session.add_all([job2, job3])
    db_session.commit()

    graph = compute_cooccurrence_graph(db_session, min_weight=1, max_nodes=20)
    assert graph.total_skills > 0
    assert graph.total_connections > 0
    assert len(graph.nodes) == graph.total_skills
    assert len(graph.edges) == graph.total_connections
    assert len(graph.clusters) > 0

    # Verify edge attributes
    edge = graph.edges[0]
    assert edge.weight >= 1
    assert edge.lift is not None
    assert edge.support is not None
    assert edge.source != edge.target

    # Verify node attributes
    node = graph.nodes[0]
    assert node.id
    assert node.value >= 1
    assert node.category


def test_sync_cooccurrences_to_db(db_session):
    """Verify persisting pairwise co-occurrences into database."""
    synced = sync_cooccurrences_to_db(db_session, region="Latin America")
    assert synced > 0

    records = db_session.scalars(
        select(SkillCooccurrence).where(SkillCooccurrence.region == "Latin America")
    ).all()
    assert len(records) > 0
    assert records[0].pair_key is not None
    assert records[0].cooccurrence_count >= 1


# ---------------------------------------------------------
# API Endpoints Integration Tests
# ---------------------------------------------------------

def test_api_analytics_skills(client):
    """Test GET /api/v1/analytics/skills endpoint."""
    response = client.get("/api/v1/analytics/skills")
    assert response.status_code == 200
    data = response.json()

    assert "total_jobs" in data
    assert "top_skills" in data
    assert data["total_jobs"] >= 1
    assert len(data["top_skills"]) > 0

    top_skill = data["top_skills"][0]
    assert "name" in top_skill
    assert "count" in top_skill
    assert "percentage" in top_skill
    assert "category" in top_skill


def test_api_analytics_skills_with_region(client):
    """Test GET /api/v1/analytics/skills with region filter."""
    response = client.get("/api/v1/analytics/skills?region=Latin%20America&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["region"] == "Latin America"
    assert len(data["top_skills"]) <= 5


def test_api_analytics_graph(client):
    """Test GET /api/v1/analytics/graph endpoint."""
    response = client.get("/api/v1/analytics/graph?min_weight=1&max_nodes=15")
    assert response.status_code == 200
    data = response.json()

    assert "nodes" in data
    assert "edges" in data
    assert "clusters" in data
    assert "total_skills" in data
    assert "total_connections" in data

    if data["edges"]:
        edge = data["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "weight" in edge
        assert "lift" in edge
        assert "support" in edge


def test_api_analytics_taxonomies(client):
    """Test GET /api/v1/analytics/taxonomies endpoint."""
    response = client.get("/api/v1/analytics/taxonomies")
    assert response.status_code == 200
    data = response.json()

    assert "categories" in data
    assert "total_nodes" in data
    assert data["total_nodes"] >= 7
    assert len(data["categories"]) >= 7

    # Check structure of first category
    cat = data["categories"][0]
    assert "code" in cat
    assert "name" in cat
    assert "children" in cat


def test_api_analytics_taxonomy_normalize(client):
    """Test POST /api/v1/analytics/taxonomy/normalize endpoint."""
    settings.ADMIN_API_KEY = "test-operator-secret-taxonomy-tests-32"
    headers = {"Authorization": "Bearer test-operator-secret-taxonomy-tests-32"}
    payload = {
        "skills": ["k8s", "react.js", "postgres", "fast api", "aws"]
    }
    response = client.post(
        "/api/v1/analytics/taxonomy/normalize", json=payload, headers=headers
    )
    assert response.status_code == 200
    data = response.json()

    assert "normalized" in data
    items = data["normalized"]
    assert len(items) == 5

    names = {item["canonical_name"] for item in items}
    assert "Kubernetes" in names
    assert "React" in names
    assert "PostgreSQL" in names
    assert "FastAPI" in names
    assert "Amazon Web Services (AWS)" in names
