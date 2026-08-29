"""Establish Alembic authority over runtime schema and reconcile create_all databases.

Revision ID: 0011_runtime_schema_authority
Revises: 0010_pgvector_taxonomies
Create Date: 2026-08-28 00:00:00.000000

Pre-existing create_all databases must be stamped once:
    alembic stamp 0010_pgvector_taxonomies
before applying this migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_runtime_schema_authority"
down_revision = "0010_pgvector_taxonomies"
branch_labels = None
depends_on = None

_OWNERSHIP_TABLE = "skillpulse_0011_ownership"


def _record_owned(bind, object_name: str) -> None:
    bind.execute(
        sa.text(
            f"INSERT INTO {_OWNERSHIP_TABLE} (object_name) VALUES (:object_name)"
        ),
        {"object_name": object_name},
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_OWNERSHIP_TABLE):
        op.create_table(
            _OWNERSHIP_TABLE,
            sa.Column("object_name", sa.String(length=255), primary_key=True),
        )
    inspector = sa.inspect(bind)

    # 1. Inspect and reconcile `jobs.source`
    if inspector.has_table("jobs"):
        columns = {c["name"]: c for c in inspector.get_columns("jobs")}
        indexes = {idx["name"] for idx in inspector.get_indexes("jobs")}
        if "source" not in columns:
            _record_owned(bind, "column:jobs.source")
            _record_owned(bind, "index:ix_jobs_source")
            with op.batch_alter_table("jobs", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("source", sa.String(length=50), nullable=False, server_default="gupy")
                )
                batch_op.create_index("ix_jobs_source", ["source"], unique=False)
        else:
            col = columns["source"]
            col_type = col["type"]
            if not isinstance(col_type, (sa.String, sa.VARCHAR, sa.Text)):
                raise RuntimeError(f"Incompatible column type for jobs.source: {col_type}")

            if col.get("nullable", True):
                _record_owned(bind, "nullability:jobs.source")
                op.execute("UPDATE jobs SET source = 'gupy' WHERE source IS NULL;")
                with op.batch_alter_table("jobs", schema=None) as batch_op:
                    batch_op.alter_column(
                        "source",
                        existing_type=sa.String(length=50),
                        nullable=False,
                        server_default="gupy",
                    )
            if "ix_jobs_source" not in indexes:
                _record_owned(bind, "index:ix_jobs_source")
                with op.batch_alter_table("jobs", schema=None) as batch_op:
                    batch_op.create_index("ix_jobs_source", ["source"], unique=False)

    # 2. Inspect and reconcile `jobs_posts.source`
    if inspector.has_table("jobs_posts"):
        columns = {c["name"]: c for c in inspector.get_columns("jobs_posts")}
        indexes = {idx["name"] for idx in inspector.get_indexes("jobs_posts")}
        if "source" not in columns:
            _record_owned(bind, "column:jobs_posts.source")
            _record_owned(bind, "index:ix_jobs_posts_source")
            with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("source", sa.String(length=50), nullable=False, server_default="gupy")
                )
                batch_op.create_index("ix_jobs_posts_source", ["source"], unique=False)
        else:
            col = columns["source"]
            col_type = col["type"]
            if not isinstance(col_type, (sa.String, sa.VARCHAR, sa.Text)):
                raise RuntimeError(f"Incompatible column type for jobs_posts.source: {col_type}")

            if col.get("nullable", True):
                _record_owned(bind, "nullability:jobs_posts.source")
                op.execute("UPDATE jobs_posts SET source = 'gupy' WHERE source IS NULL;")
                with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
                    batch_op.alter_column(
                        "source",
                        existing_type=sa.String(length=50),
                        nullable=False,
                        server_default="gupy",
                    )
            if "ix_jobs_posts_source" not in indexes:
                _record_owned(bind, "index:ix_jobs_posts_source")
                with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
                    batch_op.create_index("ix_jobs_posts_source", ["source"], unique=False)

    # 3. Create `admin_sessions` table if absent, else verify columns
    if not inspector.has_table("admin_sessions"):
        _record_owned(bind, "table:admin_sessions")
        op.create_table(
            "admin_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("admin_sessions", schema=None) as batch_op:
            batch_op.create_index("ix_admin_sessions_token_hash", ["token_hash"], unique=True)
            batch_op.create_index("ix_admin_sessions_expires_at", ["expires_at"], unique=False)
    else:
        existing_cols = {c["name"] for c in inspector.get_columns("admin_sessions")}
        required_cols = {"id", "token_hash", "issued_at", "expires_at", "revoked_at", "last_seen_at"}
        missing = required_cols - existing_cols
        if missing:
            raise RuntimeError(f"Pre-existing admin_sessions table missing columns: {missing}")

    # 4. Create `llm_extractions` table if absent, else verify columns
    if not inspector.has_table("llm_extractions"):
        _record_owned(bind, "table:llm_extractions")
        op.create_table(
            "llm_extractions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="groq"),
            sa.Column("model", sa.String(length=100), nullable=False, server_default="llama-3.3-70b-versatile"),
            sa.Column("prompt_version", sa.String(length=20), nullable=False, server_default="v1.0"),
            sa.Column("response_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("llm_extractions", schema=None) as batch_op:
            batch_op.create_index("ix_llm_extractions_fingerprint", ["fingerprint"], unique=True)
    else:
        existing_cols = {c["name"] for c in inspector.get_columns("llm_extractions")}
        required_cols = {"id", "fingerprint", "provider", "model", "prompt_version", "response_json", "created_at"}
        missing = required_cols - existing_cols
        if missing:
            raise RuntimeError(f"Pre-existing llm_extractions table missing columns: {missing}")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    owned: set[str] = set()
    if inspector.has_table(_OWNERSHIP_TABLE):
        owned = set(
            bind.execute(sa.text(f"SELECT object_name FROM {_OWNERSHIP_TABLE}"))
            .scalars()
            .all()
        )

    if "table:llm_extractions" in owned and inspector.has_table("llm_extractions"):
        op.drop_table("llm_extractions")

    if "table:admin_sessions" in owned and inspector.has_table("admin_sessions"):
        op.drop_table("admin_sessions")

    if inspector.has_table("jobs_posts"):
        indexes = {idx["name"] for idx in inspector.get_indexes("jobs_posts")}
        cols = {c["name"] for c in inspector.get_columns("jobs_posts")}
        with op.batch_alter_table("jobs_posts", schema=None) as batch_op:
            if "index:ix_jobs_posts_source" in owned and "ix_jobs_posts_source" in indexes:
                batch_op.drop_index("ix_jobs_posts_source")
            if (
                "source" in cols
                and {
                    "column:jobs_posts.source",
                    "nullability:jobs_posts.source",
                }
                & owned
            ):
                batch_op.alter_column(
                    "source",
                    existing_type=sa.String(length=50),
                    nullable=True,
                    server_default=None,
                )

    if inspector.has_table("jobs"):
        indexes = {idx["name"] for idx in inspector.get_indexes("jobs")}
        cols = {c["name"] for c in inspector.get_columns("jobs")}
        with op.batch_alter_table("jobs", schema=None) as batch_op:
            if "index:ix_jobs_source" in owned and "ix_jobs_source" in indexes:
                batch_op.drop_index("ix_jobs_source")
            if (
                "source" in cols
                and {"column:jobs.source", "nullability:jobs.source"} & owned
            ):
                batch_op.alter_column(
                    "source",
                    existing_type=sa.String(length=50),
                    nullable=True,
                    server_default=None,
                )

    inspector = sa.inspect(bind)
    if inspector.has_table(_OWNERSHIP_TABLE):
        op.drop_table(_OWNERSHIP_TABLE)
