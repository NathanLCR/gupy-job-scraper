from alembic import op
import sqlalchemy as sa

revision = "0007_add_seniority_to_jobs"
down_revision = "0006_add_last_scraped_at"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("jobs", sa.Column("seniority", sa.String(length=50), nullable=True))
    op.add_column("jobs", sa.Column("years_experience", sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column("jobs", "years_experience")
    op.drop_column("jobs", "seniority")
