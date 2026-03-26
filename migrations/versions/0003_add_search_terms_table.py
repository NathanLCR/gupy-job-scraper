from alembic import op
import sqlalchemy as sa


revision = "0003_add_search_terms_table"
down_revision = "0002_add_error_logs_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_terms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term"),
    )

    op.bulk_insert(
        sa.table(
            "search_terms",
            sa.column("term", sa.String),
            sa.column("is_active", sa.Boolean),
        ),
        [
            {"term": "Desenvolvedor", "is_active": True},
            {"term": "Engenheiro de software", "is_active": True},
            {"term": "Developer", "is_active": True},
            {"term": "software engineer", "is_active": True},
            {"term": "data science", "is_active": True},
            {"term": "Cientista de dados", "is_active": True},
            {"term": "Tech lead", "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("search_terms")
