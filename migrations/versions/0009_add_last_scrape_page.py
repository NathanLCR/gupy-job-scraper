from alembic import op
import sqlalchemy as sa


revision = "0009_add_last_scrape_page"
down_revision = "0008_seed_search_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_terms", sa.Column("last_scrape_page", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("search_terms", "last_scrape_page")
