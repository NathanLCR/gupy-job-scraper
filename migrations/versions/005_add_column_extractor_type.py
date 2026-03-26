from alembic import op
import sqlalchemy as sa

revision = "0005_add_column_extractor_type"
down_revision = "0004_add_jobs_posts_table"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("jobs", sa.Column("extractor_type", sa.String(length=50), nullable=True))

def downgrade() -> None:
    op.drop_column("jobs", "extractor_type")