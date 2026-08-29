import pytest
from sqlalchemy import text

from tests.postgres_support import postgres_engine


@pytest.mark.postgres
def test_postgres_16_pgvector_harness_is_at_alembic_head(postgres_engine):
    with postgres_engine.connect() as connection:
        assert int(connection.execute(text("SHOW server_version_num")).scalar_one()) >= 160000
        assert connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")
        ).scalar_one() is True
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == "0012_postgres_indexed_retrieval"
