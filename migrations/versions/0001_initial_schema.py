"""Initial schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "contract_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "hard_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "soft_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "nice_to_have_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False),
        sa.Column("salary", sa.Integer(), nullable=True),
        sa.Column("tech_stack", sa.JSON(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("contract_type_id", sa.Integer(), nullable=True),
        sa.Column("state_id", sa.Integer(), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["contract_type_id"], ["contract_types.id"]),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_hard_skills",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("hard_skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["hard_skill_id"], ["hard_skills.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("job_id", "hard_skill_id"),
    )

    op.create_table(
        "job_soft_skills",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("soft_skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["soft_skill_id"], ["soft_skills.id"]),
        sa.PrimaryKeyConstraint("job_id", "soft_skill_id"),
    )

    op.create_table(
        "job_nice_to_have_skills",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("nice_to_have_skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["nice_to_have_skill_id"], ["nice_to_have_skills.id"]),
        sa.PrimaryKeyConstraint("job_id", "nice_to_have_skill_id"),
    )


def downgrade() -> None:
    op.drop_table("job_nice_to_have_skills")
    op.drop_table("job_soft_skills")
    op.drop_table("job_hard_skills")
    op.drop_table("jobs")
    op.drop_table("cities")
    op.drop_table("nice_to_have_skills")
    op.drop_table("soft_skills")
    op.drop_table("hard_skills")
    op.drop_table("states")
    op.drop_table("contract_types")
    op.drop_table("companies")
