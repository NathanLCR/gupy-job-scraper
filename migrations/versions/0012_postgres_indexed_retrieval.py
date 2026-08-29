"""Add PostgreSQL indexed retrieval documents and embedding provenance.

Revision ID: 0012_postgres_indexed_retrieval
Revises: 0011_runtime_schema_authority
Create Date: 2026-08-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_postgres_indexed_retrieval"
down_revision = "0011_runtime_schema_authority"
branch_labels = None
depends_on = None


def _replace_hnsw_with_partial() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_jobs_embedding_hnsw_partial "
            "ON jobs USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64) WHERE embedding IS NOT NULL"
        )
        valid = op.get_bind().execute(
            sa.text(
                "SELECT i.indisvalid FROM pg_index i "
                "JOIN pg_class c ON c.oid=i.indexrelid "
                "WHERE c.relname='ix_jobs_embedding_hnsw_partial'"
            )
        ).scalar_one_or_none()
        if valid is not True:
            raise RuntimeError("partial HNSW index validation failed")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_jobs_embedding_hnsw")
        op.execute(
            "ALTER INDEX ix_jobs_embedding_hnsw_partial "
            "RENAME TO ix_jobs_embedding_hnsw"
        )


def _replace_hnsw_with_full() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_jobs_embedding_hnsw_full "
            "ON jobs USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        valid = op.get_bind().execute(
            sa.text(
                "SELECT i.indisvalid FROM pg_index i "
                "JOIN pg_class c ON c.oid=i.indexrelid "
                "WHERE c.relname='ix_jobs_embedding_hnsw_full'"
            )
        ).scalar_one_or_none()
        if valid is not True:
            raise RuntimeError("full HNSW index validation failed")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_jobs_embedding_hnsw")
        op.execute(
            "ALTER INDEX ix_jobs_embedding_hnsw_full "
            "RENAME TO ix_jobs_embedding_hnsw"
        )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "search_document",
                postgresql.TSVECTOR() if is_postgres else sa.Text(),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("embedding_model", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True)
        )

    if not is_postgres:
        return

    op.execute(
        "CREATE INDEX ix_jobs_search_document_gin "
        "ON jobs USING gin (search_document)"
    )

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION refresh_job_search_document(target_job_id bigint)
        RETURNS void LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE jobs AS target
          SET search_document = source.document
          FROM (
            SELECT j.id,
              setweight(to_tsvector('english', coalesce(j.job_title, '')), 'A') ||
              setweight(to_tsvector('english', coalesce((
                SELECT string_agg(DISTINCT hs.name, ' ')
                FROM job_hard_skills jhs
                JOIN hard_skills hs ON hs.id = jhs.hard_skill_id
                WHERE jhs.job_id = j.id
              ), '')), 'A') ||
              setweight(to_tsvector('english', coalesce(c.name, '')), 'B') ||
              setweight(to_tsvector('english', coalesce((
                SELECT string_agg(value, ' ')
                FROM jsonb_array_elements_text(
                  coalesce(j.tech_stack::jsonb, '[]'::jsonb)
                ) AS value
              ), '')), 'B') ||
              setweight(to_tsvector('english', concat_ws(' ',
                j.seniority, ci.name, st.name, j.region, j.workplace_type
              )), 'C') ||
              setweight(to_tsvector('english', coalesce(j.description, '')), 'D')
              AS document
            FROM jobs j
            LEFT JOIN companies c ON c.id = j.company_id
            LEFT JOIN cities ci ON ci.id = j.city_id
            LEFT JOIN states st ON st.id = j.state_id
            WHERE j.id = target_job_id
          ) AS source
          WHERE target.id = source.id;
        END;
        $$
        """
    )

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION jobs_refresh_search_document_trigger()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_job_search_document(NEW.id);
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION jobs_invalidate_embedding_trigger()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND (
            NEW.job_title IS DISTINCT FROM OLD.job_title OR
            NEW.tech_stack IS DISTINCT FROM OLD.tech_stack OR
            NEW.description IS DISTINCT FROM OLD.description OR
            NEW.seniority IS DISTINCT FROM OLD.seniority
          ) THEN
            NEW.embedding := NULL;
            NEW.embedding_model := NULL;
            NEW.embedding_updated_at := NULL;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION job_hard_skills_refresh_search_document_trigger()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_id bigint;
        BEGIN
          IF pg_trigger_depth() > 1 THEN
            RETURN coalesce(NEW, OLD);
          END IF;
          target_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.job_id ELSE NEW.job_id END;
          UPDATE jobs SET embedding=NULL, embedding_model=NULL,
            embedding_updated_at=NULL WHERE id=target_id;
          PERFORM refresh_job_search_document(target_id);
          RETURN coalesce(NEW, OLD);
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION hard_skills_refresh_search_document_trigger()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_id bigint;
        BEGIN
          IF pg_trigger_depth() > 1 THEN RETURN NEW; END IF;
          FOR target_id IN
            SELECT job_id FROM job_hard_skills WHERE hard_skill_id=NEW.id
          LOOP
            UPDATE jobs SET embedding=NULL, embedding_model=NULL,
              embedding_updated_at=NULL WHERE id=target_id;
            PERFORM refresh_job_search_document(target_id);
          END LOOP;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION companies_refresh_search_document_trigger()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_id bigint;
        BEGIN
          FOR target_id IN SELECT id FROM jobs WHERE company_id=NEW.id
          LOOP
            PERFORM refresh_job_search_document(target_id);
          END LOOP;
          RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        "CREATE TRIGGER trg_jobs_invalidate_embedding "
        "BEFORE INSERT OR UPDATE OF job_title, tech_stack, description, seniority ON jobs "
        "FOR EACH ROW EXECUTE FUNCTION jobs_invalidate_embedding_trigger()"
    )
    op.execute(
        "CREATE TRIGGER trg_jobs_refresh_search_document "
        "AFTER INSERT OR UPDATE OF job_title, tech_stack, description, seniority, "
        "company_id, city_id, state_id, region, workplace_type ON jobs "
        "FOR EACH ROW EXECUTE FUNCTION jobs_refresh_search_document_trigger()"
    )
    op.execute(
        "CREATE TRIGGER trg_job_hard_skills_refresh_search_document "
        "AFTER INSERT OR DELETE ON job_hard_skills FOR EACH ROW "
        "EXECUTE FUNCTION job_hard_skills_refresh_search_document_trigger()"
    )
    op.execute(
        "CREATE TRIGGER trg_hard_skills_refresh_search_document "
        "AFTER UPDATE OF name ON hard_skills FOR EACH ROW "
        "EXECUTE FUNCTION hard_skills_refresh_search_document_trigger()"
    )
    op.execute(
        "CREATE TRIGGER trg_companies_refresh_search_document "
        "AFTER UPDATE OF name ON companies FOR EACH ROW "
        "EXECUTE FUNCTION companies_refresh_search_document_trigger()"
    )

    _replace_hnsw_with_partial()


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS trg_jobs_invalidate_embedding ON jobs")
        op.execute("DROP TRIGGER IF EXISTS trg_jobs_refresh_search_document ON jobs")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_job_hard_skills_refresh_search_document "
            "ON job_hard_skills"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_hard_skills_refresh_search_document ON hard_skills"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_companies_refresh_search_document ON companies"
        )
        op.execute("DROP FUNCTION IF EXISTS jobs_invalidate_embedding_trigger()")
        op.execute("DROP FUNCTION IF EXISTS jobs_refresh_search_document_trigger()")
        op.execute(
            "DROP FUNCTION IF EXISTS job_hard_skills_refresh_search_document_trigger()"
        )
        op.execute("DROP FUNCTION IF EXISTS hard_skills_refresh_search_document_trigger()")
        op.execute("DROP FUNCTION IF EXISTS companies_refresh_search_document_trigger()")
        op.execute("DROP FUNCTION IF EXISTS refresh_job_search_document(bigint)")
        op.execute("DROP INDEX IF EXISTS ix_jobs_search_document_gin")
        _replace_hnsw_with_full()

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("embedding_updated_at")
        batch_op.drop_column("embedding_model")
        batch_op.drop_column("search_document")
