from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert


revision = "0008_seed_search_terms"
down_revision = "0007_add_seniority_to_jobs"
branch_labels = None
depends_on = None


search_terms = sa.table(
    "search_terms",
    sa.column("term", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("last_scraped_at", sa.DateTime(timezone=True)),
)


TERMS_TO_INSERT = [
    "Software Engineer",
    "Mobile Engineer",
    "Data Scientist",
    "Cientista de Dados",
    "Data Engineer",
    "Machine Learning Engineer",
    "ML Engineer",
    "AI Engineer",
    "DevOps",
    "Cloud Architect",
    "SRE",
    "QA Engineer",
    "Quality Assurance",
    "SDET",
    "Software",
    "Desenvolvedor",
    "Developer",
]


def upgrade() -> None:
    bind = op.get_bind()

    for term in TERMS_TO_INSERT:
        stmt = insert(search_terms).values(
            term=term,
            is_active=True,
            last_scraped_at=None,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["term"])
        bind.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    removable_terms = [
        term for term in TERMS_TO_INSERT if term not in {"Desenvolvedor", "Developer"}
    ]

    delete_stmt = sa.delete(search_terms).where(
        search_terms.c.term.in_(removable_terms)
    )
    bind.execute(delete_stmt)
