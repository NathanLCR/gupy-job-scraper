import os
import sys
from pathlib import Path

# Insert project root to sys.path
root_dir = str(Path(__file__).resolve().parents[1])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Point to a temporary test SQLite database for test runs
test_db_path = os.path.join(root_dir, "test_jobs.db")
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

from config import settings
settings.RATE_LIMIT_ENABLED = False

import database
database._engine = None
database._session_factory = None

import pytest
from alembic import command
from alembic.config import Config
from database import get_engine, SessionLocal
from entities import Base, SearchTerm, Company, City, State, ContractType, Job, HardSkill
from entities.associations import job_hard_skills
from services.taxonomy_service import seed_default_taxonomy
from services.rate_limit_service import RateLimitDecision


class InMemoryLoginLimiter:
    """Per-test shared limiter used to keep unit tests independent of real Redis."""

    def __init__(self):
        self.counts = {}

    def _decision(self, subject, limit, window_seconds):
        count = self.counts.get(subject, 0)
        blocked = count >= limit
        return RateLimitDecision(
            allowed=not blocked,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=window_seconds if blocked else 0,
            reset_after_seconds=window_seconds if count else 0,
        )

    def peek(self, scope, subject, limit, window_seconds):
        return self._decision(subject, limit, window_seconds)

    def record(self, scope, subject, limit, window_seconds):
        self.counts[subject] = self.counts.get(subject, 0) + 1
        return self._decision(subject, limit, window_seconds)

    def clear(self, scope, subject):
        self.counts.pop(subject, None)


@pytest.fixture(autouse=True)
def unit_login_limiter(monkeypatch):
    limiter = InMemoryLoginLimiter()
    monkeypatch.setattr("api.v1.auth.get_rate_limiter", lambda: limiter)
    return limiter


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "redis_integration: mark test as requiring a real Redis instance"
    )
    config.addinivalue_line(
        "markers", "postgres: mark test as requiring PostgreSQL 16 with pgvector"
    )
    config.addinivalue_line(
        "markers", "postgres_performance: mark representative PostgreSQL plan/timing tests"
    )



@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    # Remove existing test sqlite file if present
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass

    database._engine = None
    database._session_factory = None

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "migrations")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db_path}")
    command.upgrade(alembic_cfg, "head")

    # Seed some sample data for testing endpoints
    db = SessionLocal()
    try:
        # Seed default taxonomy and aliases
        seed_default_taxonomy(db)

        # Search Terms
        existing_terms = {t.term for t in db.query(SearchTerm).all()}
        for term_str in ["Python Developer", "Data Scientist"]:
            if term_str not in existing_terms:
                db.add(SearchTerm(term=term_str, is_active=True))

        # Company, State, City, Contract
        comp = Company(name="Tech Corp Inc")
        state = State(name="São Paulo")
        db.add(comp)
        db.add(state)
        db.flush()

        city = City(name="São Paulo", state_id=state.id)
        contract = ContractType(name="CLT")
        skill1 = HardSkill(name="Python")
        skill2 = HardSkill(name="FastAPI")
        skill3 = HardSkill(name="Docker")
        db.add_all([city, contract, skill1, skill2, skill3])
        db.flush()

        job1 = Job(
            job_title="Senior Python Developer",
            extractor_type="regex",
            salary=18000,
            seniority="Senior",
            years_experience=5,
            tech_stack=["Python", "FastAPI", "Docker"],
            region="Latin America",
            country_code="BR",
            currency="BRL",
            workplace_type="REMOTE",
            company_id=comp.id,
            contract_type_id=contract.id,
            state_id=state.id,
            city_id=city.id,
            hard_skills=[skill1, skill2, skill3],
        )
        db.add(job1)
        db.commit()
    finally:
        db.close()

    yield

    # Teardown
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass
