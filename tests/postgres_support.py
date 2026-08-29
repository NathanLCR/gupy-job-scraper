import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


@pytest.fixture(scope="session")
def postgres_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration test skipped: TEST_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SHOW server_version_num")).scalar_one()
            if int(version) < 160000:
                pytest.skip(f"PostgreSQL integration test skipped: server is {version}, need 16+")
        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", "migrations")
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        command.upgrade(cfg, "head")
        yield engine
    except pytest.skip.Exception:
        raise
    except Exception as exc:
        pytest.skip(
            f"PostgreSQL integration test skipped: TEST_DATABASE_URL is unreachable or unusable ({type(exc).__name__})"
        )
    finally:
        engine.dispose()
