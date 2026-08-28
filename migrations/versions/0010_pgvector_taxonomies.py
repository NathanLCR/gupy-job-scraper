"""Upgrade schema with pgvector, HNSW indexing, multi-region fields, canonical taxonomies, and candidate profiles.

Revision ID: 0010_pgvector_taxonomies
Revises: 0009_add_last_scrape_page
Create Date: 2026-08-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_pgvector_taxonomies"
down_revision = "0009_add_last_scrape_page"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Enable pgvector extension on PostgreSQL
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Add Multi-Region and Embedding columns to `jobs`
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("region", sa.String(length=50), nullable=False, server_default="Latin America")
        )
        batch_op.add_column(
            sa.Column("country_code", sa.String(length=10), nullable=False, server_default="BR")
        )
        batch_op.add_column(
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL")
        )
        batch_op.add_column(
            sa.Column("workplace_type", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("description", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now())
        )
        if not is_postgres:
            batch_op.add_column(
                sa.Column("embedding", sa.JSON(), nullable=True)
            )

    if is_postgres:
        op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding vector(384);")

    # 3. Add Multi-Region columns to `jobs_posts`
    with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("region", sa.String(length=50), nullable=False, server_default="Latin America")
        )
        batch_op.add_column(
            sa.Column("country_code", sa.String(length=10), nullable=False, server_default="BR")
        )
        batch_op.add_column(
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL")
        )
        batch_op.add_column(
            sa.Column("fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now())
        )

    # 4. Create `candidate_profiles` table
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("raw_resume_text", sa.Text(), nullable=False),
        sa.Column("parsed_skills", sa.JSON(), nullable=True),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("target_region", sa.String(length=50), nullable=True, server_default="Global"),
        sa.Column("target_role", sa.String(length=255), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    if is_postgres:
        op.execute("ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS embedding vector(384);")
    else:
        with op.batch_alter_table("candidate_profiles", schema=None) as batch_op:
            batch_op.add_column(sa.Column("embedding", sa.JSON(), nullable=True))

    # 5. Create `taxonomy_nodes` table
    op.create_table(
        "taxonomy_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["parent_id"], ["taxonomy_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # 6. Create `skill_aliases` table
    op.create_table(
        "skill_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alias", sa.String(length=150), nullable=False),
        sa.Column("canonical_name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="technical"),
        sa.Column("esco_uri", sa.String(length=255), nullable=True),
        sa.Column("onet_code", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias"),
    )

    # 7. Create `skill_cooccurrences` table
    op.create_table(
        "skill_cooccurrences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("skill_a", sa.String(length=150), nullable=False),
        sa.Column("skill_b", sa.String(length=150), nullable=False),
        sa.Column("pair_key", sa.String(length=300), nullable=False),
        sa.Column("cooccurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("region", sa.String(length=50), nullable=False, server_default="Global"),
        sa.Column("last_updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pair_key", name="uq_skill_cooccurrences_pair_key"),
    )

    # 8. Create Indexes & HNSW Vector Index on PostgreSQL
    if is_postgres:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_jobs_embedding_hnsw ON jobs "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_candidate_profiles_embedding_hnsw ON candidate_profiles "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
        )

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index("ix_jobs_fingerprint", ["fingerprint"], unique=False)

    with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
        batch_op.create_index("ix_jobs_posts_fingerprint", ["fingerprint"], unique=False)

    with op.batch_alter_table("skill_aliases", schema=None) as batch_op:
        batch_op.create_index("ix_skill_aliases_canonical", ["canonical_name"], unique=False)

    with op.batch_alter_table("skill_cooccurrences", schema=None) as batch_op:
        batch_op.create_index("ix_skill_cooccurrences_skill_a", ["skill_a"], unique=False)
        batch_op.create_index("ix_skill_cooccurrences_skill_b", ["skill_b"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_jobs_embedding_hnsw;")
        op.execute("DROP INDEX IF EXISTS ix_candidate_profiles_embedding_hnsw;")

    op.drop_table("skill_cooccurrences")
    op.drop_table("skill_aliases")
    op.drop_table("taxonomy_nodes")
    op.drop_table("candidate_profiles")

    with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
        batch_op.drop_index("ix_jobs_posts_fingerprint")
        batch_op.drop_column("created_at")
        batch_op.drop_column("fingerprint")
        batch_op.drop_column("currency")
        batch_op.drop_column("country_code")
        batch_op.drop_column("region")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_jobs_fingerprint")
        batch_op.drop_column("embedding")
        batch_op.drop_column("created_at")
        batch_op.drop_column("description")
        batch_op.drop_column("fingerprint")
        batch_op.drop_column("workplace_type")
        batch_op.drop_column("currency")
        batch_op.drop_column("country_code")
        batch_op.drop_column("region")
