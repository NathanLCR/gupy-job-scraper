from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_add_last_scraped_at"
down_revision = "0005_add_column_extractor_type"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("search_terms", sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("search_terms", "last_scraped_at")
