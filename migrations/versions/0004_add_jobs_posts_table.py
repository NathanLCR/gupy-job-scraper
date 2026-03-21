"""Add jobs posts table.

Revision ID: 0004_add_jobs_posts_table
Revises: 0003_add_search_terms_table
Create Date: 2026-03-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_add_jobs_posts_table"
down_revision = "0003_add_search_terms_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs_posts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("career_page_id", sa.BigInteger(), nullable=True),
        sa.Column("career_page_name", sa.String(length=255), nullable=True),
        sa.Column("career_page_logo", sa.Text(), nullable=True),
        sa.Column("career_page_url", sa.Text(), nullable=True),
        sa.Column("job_type", sa.String(length=100), nullable=True),
        sa.Column("published_date", sa.DateTime(), nullable=True),
        sa.Column("application_deadline", sa.Date(), nullable=True),
        sa.Column("is_remote_work", sa.Boolean(), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("job_url", sa.Text(), nullable=True),
        sa.Column("workplace_type", sa.String(length=80), nullable=True),
        sa.Column("disabilities", sa.Boolean(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("badges", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("jobs_posts")
