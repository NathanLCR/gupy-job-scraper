from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from config import settings
from schemas.job import HybridSearchRequest
from services import hybrid_search_service as hybrid
from services.postgres_retrieval_service import RankedCandidate, RetrievalResult


@pytest.mark.parametrize("query", ["", " ", "\n\t"])
def test_hybrid_request_rejects_whitespace_only_query(query):
    with pytest.raises(ValidationError):
        HybridSearchRequest(query=query)


def test_hybrid_request_rejects_zero_total_weights():
    with pytest.raises(ValidationError):
        HybridSearchRequest(query="python", dense_weight=0, sparse_weight=0)


def test_hybrid_request_rejects_excessive_text():
    with pytest.raises(ValidationError):
        HybridSearchRequest(query="x" * 4001)


def test_hybrid_request_trims_query_and_normalizes_weights():
    request = HybridSearchRequest(
        query="  python backend  ", dense_weight=2, sparse_weight=1
    )
    assert request.query == "python backend"
    assert request.dense_weight == pytest.approx(2 / 3)
    assert request.sparse_weight == pytest.approx(1 / 3)


def test_indexed_hybrid_path_loads_only_fused_ids(monkeypatch):
    job = SimpleNamespace(id=42, to_dict=lambda: {"id": 42, "job_title": "Python"})

    class FakeScalars:
        def unique(self):
            return self

        def all(self):
            return [job]

    class FakeDB:
        def scalars(self, statement):
            return FakeScalars()

    class FakeRepository:
        def __init__(self, db):
            pass

        def retrieve(self, *args, **kwargs):
            return RetrievalResult(
                candidates=(
                    RankedCandidate(42, 0.01, 1, 0.9, None, None),
                ),
                mode="dense",
            )

    monkeypatch.setattr(settings, "POSTGRES_INDEXED_RETRIEVAL_ENABLED", True, raising=False)
    monkeypatch.setattr(hybrid, "PostgresRetrievalService", FakeRepository, raising=False)

    results = hybrid.hybrid_search_jobs("python", db=FakeDB(), top_k=5)

    assert results.retrieval_mode == "dense"
    assert [item.job_id for item in results] == [42]
    assert results[0].sparse_rank is None
