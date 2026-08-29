import logging
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
import redis

from config import settings
from database import get_engine

logger = logging.getLogger("skillpulse.readiness")


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    database: Literal["connected", "unavailable"]
    schema_state: Literal["current", "outdated", "unknown"]  # NOT `schema` — shadows BaseModel
    failure_category: Optional[str] = None
    public_message: Optional[str] = None


@dataclass(frozen=True)
class DependencyReadiness:
    status: Literal["connected", "degraded"]


def _check_redis_readiness_sync(timeout_seconds: float) -> DependencyReadiness:
    if not settings.RATE_LIMIT_ENABLED:
        return DependencyReadiness(status="connected")
    if not settings.REDIS_URL:
        return DependencyReadiness(status="degraded")
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            decode_responses=False,
        )
        client.ping()
        return DependencyReadiness(status="connected")
    except Exception:
        logger.error(
            "redis_readiness_degraded",
            extra={"event": "redis_readiness_degraded"},
        )
        return DependencyReadiness(status="degraded")


def check_redis_readiness(timeout_seconds: float = 1.0) -> DependencyReadiness:
    """Report Redis state within one wall-clock deadline without leaking details."""
    results: queue.Queue[DependencyReadiness] = queue.Queue(maxsize=1)

    def run_check() -> None:
        results.put(_check_redis_readiness_sync(timeout_seconds))

    worker = threading.Thread(target=run_check, daemon=True, name="redis-readiness")
    worker.start()
    worker.join(max(0.001, timeout_seconds))
    if worker.is_alive():
        logger.error(
            "redis_readiness_degraded",
            extra={"event": "redis_readiness_degraded"},
        )
        return DependencyReadiness(status="degraded")
    return results.get_nowait()


def get_current_revision(connection: Connection) -> Optional[str]:
    context = MigrationContext.configure(connection)
    return context.get_current_revision()


def get_expected_head(config_path: str = "alembic.ini") -> Optional[str]:
    alembic_cfg = Config(config_path)
    script_location = alembic_cfg.get_main_option("script_location", "migrations")
    if not os.path.isabs(script_location):
        base_dir = Path(config_path).resolve().parent if os.path.exists(config_path) else Path.cwd()
        script_location = str(base_dir / script_location)
        alembic_cfg.set_main_option("script_location", script_location)
    script = ScriptDirectory.from_config(alembic_cfg)
    return script.get_current_head()


def _check_database_readiness_sync(timeout_seconds: float) -> ReadinessResult:
    """
    Checks database connectivity with SELECT 1 and verifies that current revision matches expected head.
    Deadline bounded. Never reveals internal exception details, hostnames, credentials, or SQL text.
    """
    try:
        engine = get_engine()
        timeout_ms = int(timeout_seconds * 1000)
        with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms};"))

            conn.execute(text("SELECT 1;"))

            current_rev = get_current_revision(conn)
            expected_head = get_expected_head()

            if current_rev is None:
                logger.error(
                    "Database readiness check failed: missing revision table",
                    extra={"failure_category": "database_schema_missing"},
                )
                return ReadinessResult(
                    ready=False,
                    database="connected",
                    schema_state="unknown",
                    failure_category="database_schema_missing",
                    public_message="Database schema is missing or unversioned.",
                )

            if current_rev != expected_head:
                logger.error(
                    "Database readiness check failed: revision mismatch",
                    extra={"failure_category": "database_schema_outdated"},
                )
                return ReadinessResult(
                    ready=False,
                    database="connected",
                    schema_state="outdated",
                    failure_category="database_schema_outdated",
                    public_message="Database schema is outdated.",
                )

            return ReadinessResult(
                ready=True,
                database="connected",
                schema_state="current",
            )

    except (TimeoutError, OperationalError) as exc:
        msg = str(exc).lower()
        if "timeout" in msg:
            logger.error(
                "database_readiness_timeout",
                extra={"event": "database_readiness_timeout"},
            )
            return ReadinessResult(
                ready=False,
                database="unavailable",
                schema_state="unknown",
                failure_category="database_readiness_timeout",
                public_message="Database connectivity check timed out.",
            )
        logger.error(
            "database_connection_failed",
            extra={"event": "database_connection_failed"},
        )
        return ReadinessResult(
            ready=False,
            database="unavailable",
            schema_state="unknown",
            failure_category="database_connection_failed",
            public_message="Database is unavailable.",
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "timeout" in msg:
            logger.error(
                "database_readiness_timeout",
                extra={"event": "database_readiness_timeout"},
            )
            return ReadinessResult(
                ready=False,
                database="unavailable",
                schema_state="unknown",
                failure_category="database_readiness_timeout",
                public_message="Database connectivity check timed out.",
            )
        logger.error(
            "database_connection_failed",
            extra={"event": "database_connection_failed"},
        )
        return ReadinessResult(
            ready=False,
            database="unavailable",
            schema_state="unknown",
            failure_category="database_connection_failed",
            public_message="Database is unavailable.",
        )


def check_database_readiness(timeout_seconds: float = 2.0) -> ReadinessResult:
    """Run the full connection/query/revision check within one wall-clock deadline."""
    results: queue.Queue[ReadinessResult] = queue.Queue(maxsize=1)

    def run_check() -> None:
        results.put(_check_database_readiness_sync(timeout_seconds))

    worker = threading.Thread(target=run_check, daemon=True, name="database-readiness")
    worker.start()
    worker.join(max(0.001, timeout_seconds))
    if worker.is_alive():
        logger.error(
            "database_readiness_timeout",
            extra={"event": "database_readiness_timeout"},
        )
        return ReadinessResult(
            ready=False,
            database="unavailable",
            schema_state="unknown",
            failure_category="database_readiness_timeout",
            public_message="Database connectivity check timed out.",
        )
    return results.get_nowait()
