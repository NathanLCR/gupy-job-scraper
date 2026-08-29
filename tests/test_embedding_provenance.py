from datetime import datetime

import pytest

from config import settings
from services import embedding_service as embedding


def test_production_provider_failure_never_returns_hash_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "cloudflare", raising=False)
    monkeypatch.setattr(settings, "ACTIVE_EMBEDDING_MODEL", settings.CF_EMBEDDING_MODEL, raising=False)
    monkeypatch.setattr(embedding, "_call_cloudflare_workers_ai", lambda texts: None)

    with pytest.raises(embedding.EmbeddingUnavailableError):
        embedding.embed_query_checked("python backend")


def test_development_hash_fallback_reports_actual_model(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "cloudflare", raising=False)
    monkeypatch.setattr(embedding, "_call_cloudflare_workers_ai", lambda texts: None)

    result = embedding.embed_query_checked("python backend")

    assert result.model == "hash-dev-v1"
    assert len(result.vector) == 384
    assert result.vector == embedding.embed_query_checked("python backend").vector


def test_extractor_embedding_fields_store_vector_model_and_timestamp(monkeypatch):
    from services import extractor_service

    result = embedding.EmbeddingResult(vector=[0.25] * 384, model="provider-model-v1")
    monkeypatch.setattr(
        extractor_service,
        "embed_job_text_checked",
        lambda **kwargs: result,
        raising=False,
    )

    fields = extractor_service.build_job_embedding_fields(
        job_title="Backend Engineer",
        tech_stack=["Python"],
        hard_skills=["Python"],
        description="Build APIs",
        seniority="Senior",
    )

    assert fields["embedding"] == result.vector
    assert fields["embedding_model"] == "provider-model-v1"
    assert isinstance(fields["embedding_updated_at"], datetime)
