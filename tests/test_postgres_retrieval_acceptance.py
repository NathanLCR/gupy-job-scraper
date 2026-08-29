import pytest

from services.postgres_retrieval_service import evaluate_retrieval_activation
from tests.postgres_support import postgres_engine


@pytest.mark.postgres
def test_activation_reports_schema_indexes_and_coverage(postgres_engine):
    from sqlalchemy.orm import Session

    with Session(postgres_engine) as db:
        status = evaluate_retrieval_activation(db)
    assert status.schema_current is True
    assert status.gin_index_valid is True
    assert status.hnsw_index_valid is True
    assert 0.0 <= status.search_document_coverage <= 1.0
    assert 0.0 <= status.embedding_coverage <= 1.0
