from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_has_no_hard_coded_test_totals_and_distinguishes_verification_tiers():
    readme = (ROOT / "README.md").read_text()
    assert "108" not in readme
    assert "215_Passing" not in readme
    assert "SQLite" in readme
    assert "PostgreSQL 16" in readme
    assert "TEST_DATABASE_URL" in readme
    assert "TEST_REDIS_URL" in readme


def test_runtime_examples_document_safe_activation_and_fail_closed_operator_auth():
    local = (ROOT / ".env.example").read_text()
    production = (ROOT / ".env.production.example").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "ADMIN_AUTH_ENABLED=true" in local
    assert 'ADMIN_API_KEY=""' in local
    assert "POSTGRES_INDEXED_RETRIEVAL_ENABLED=false" in production
    assert "backfill_job_embeddings" in readme
    assert "rollback" in readme.lower()
    assert "fail closed" in readme.lower()
