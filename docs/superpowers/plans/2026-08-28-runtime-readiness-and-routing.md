# Runtime Readiness and Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make startup, database readiness, environment examples, and `/jobs` route ownership truthful and deterministic.

**Architecture:** Alembic becomes the sole production schema authority. A focused readiness service performs database and revision checks; FastAPI exposes separate liveness/readiness endpoints and fails startup when production dependencies are not ready. Versioned API routes remain canonical while the public `/jobs` path belongs only to the SPA.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, SQLite test compatibility, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-28-runtime-readiness-and-routing-design.md`

## Global Constraints

- PostgreSQL 16 is the production database; SQLite is retained only for local/unit workflows.
- Production workers verify schema state but never run migrations or `create_all()`.
- `/health/live` performs no dependency calls; `/health/ready` and `/health` perform real readiness checks.
- Public errors must not reveal database URLs, credentials, SQL text, or migration revision identifiers.
- `/jobs` is HTML only; job JSON is served under `/api/v1/jobs` only.
- Preserve the fail-closed operator security requirements in `docs/08_admin_security_spec.md`.

---

### Task 1: Complete the Alembic-owned runtime schema

**Files:**
- Create: `migrations/versions/0011_runtime_schema_authority.py`
- Create: `tests/test_runtime_schema_migration.py`
- Modify: `database.py:78-108`
- Test: `tests/test_runtime_schema_migration.py`

**Interfaces:**
- Consumes: SQLAlchemy `Base.metadata`, current Alembic head `0010_upgrade_pgvector_taxonomies_multiregion`.
- Produces: Alembic revision `0011_runtime_schema_authority`; test-only `create_test_schema()` behavior remains in `tests/conftest.py`.

- [ ] **Step 1: Write a failing migration inventory test**

```python
def test_runtime_schema_revision_declares_missing_runtime_objects():
    migration = importlib.import_module(
        "migrations.versions.0011_runtime_schema_authority"
    )
    source = inspect.getsource(migration.upgrade)
    assert migration.down_revision == "0010_upgrade_pgvector_taxonomies_multiregion"
    assert "admin_sessions" in source
    assert "llm_extractions" in source
    assert 'add_column("source"' in source
```

Also add a PostgreSQL/SQLite migration acceptance test that upgrades a fresh database to head and verifies `admin_sessions`, `llm_extractions`, and `source` on both `jobs` and `jobs_posts`.

- [ ] **Step 2: Run the focused test and verify the missing revision fails**

Run: `.venv/bin/python -m pytest tests/test_runtime_schema_migration.py -v`

Expected: FAIL because `0011_runtime_schema_authority` does not exist.

- [ ] **Step 3: Add revision `0011_runtime_schema_authority`**

Implement an idempotent dialect-aware migration that:

```python
revision = "0011_runtime_schema_authority"
down_revision = "0010_upgrade_pgvector_taxonomies_multiregion"
```

- adds `jobs.source VARCHAR(50) NOT NULL DEFAULT 'gupy'` plus `ix_jobs_source` when absent;
- adds `jobs_posts.source VARCHAR(50) NOT NULL DEFAULT 'gupy'` plus `ix_jobs_posts_source` when absent;
- creates `admin_sessions` exactly as `entities/admin_session.py` declares it;
- creates `llm_extractions` exactly as `entities/llm_extraction_cache.py` declares it;
- creates unique/index constraints for session token hashes and extraction fingerprints;
- drops those objects in reverse dependency order in `downgrade()`.

Use SQLAlchemy inspection before compatibility column additions because current local databases may already contain runtime-created columns. Do not use `CREATE TABLE IF NOT EXISTS` to hide incompatible existing schemas: inspect and raise on incompatible types or nullability.

- [ ] **Step 4: Remove runtime column migration from `database.init_db()`**

Reduce `init_db()` to test/local schema creation only:

```python
def init_db() -> None:
    """Create model tables for isolated tests; production uses Alembic."""
    Base.metadata.create_all(bind=get_engine())
```

No `ALTER TABLE` or swallowed exception remains in `database.py`.

- [ ] **Step 5: Run migration tests in both supported test modes**

Run: `.venv/bin/python -m pytest tests/test_runtime_schema_migration.py tests/test_models.py -v`

Expected: PASS; fresh upgrades contain every runtime table/column and model tests still pass.

- [ ] **Step 6: Commit the schema authority change**

```bash
git add migrations/versions/0011_runtime_schema_authority.py database.py tests/test_runtime_schema_migration.py
git commit -m "fix: make Alembic authoritative for runtime schema"
```

---

### Task 2: Implement liveness and database readiness services

**Files:**
- Create: `services/readiness_service.py`
- Create: `tests/test_readiness_service.py`
- Modify: `schemas/common.py:15-20`
- Modify: `schemas/__init__.py:1-8,60-104`
- Test: `tests/test_readiness_service.py`

**Interfaces:**
- Consumes: `database.get_engine()`, Alembic `MigrationContext`, configured application version.
- Produces: `ReadinessResult`, `check_database_readiness(timeout_seconds: float = 2.0) -> ReadinessResult`, `LivenessResponse`, and `ReadinessResponse`.

- [ ] **Step 1: Write failing readiness-service tests**

```python
def test_readiness_requires_query_and_current_revision(monkeypatch):
    monkeypatch.setattr(readiness, "get_current_revision", lambda conn: "0011_runtime_schema_authority")
    monkeypatch.setattr(readiness, "get_expected_head", lambda: "0011_runtime_schema_authority")
    result = readiness.check_database_readiness()
    assert result.ready is True
    assert result.database == "connected"
    assert result.schema == "current"

def test_readiness_hides_internal_error(monkeypatch):
    monkeypatch.setattr(readiness, "get_engine", lambda: BrokenEngine("postgresql://secret"))
    result = readiness.check_database_readiness()
    assert result.ready is False
    assert result.failure_category == "database_connection_failed"
    assert "secret" not in result.public_message
```

Add timeout, missing revision table, and stale revision cases.

- [ ] **Step 2: Run the focused test to prove the service is absent**

Run: `.venv/bin/python -m pytest tests/test_readiness_service.py -v`

Expected: FAIL importing `services.readiness_service`.

- [ ] **Step 3: Implement the result type and revision helpers**

```python
@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    database: Literal["connected", "unavailable"]
    schema: Literal["current", "outdated", "unknown"]
    failure_category: str | None = None
    public_message: str | None = None
```

`get_current_revision(connection)` uses `MigrationContext.configure(connection).get_current_revision()`. `get_expected_head()` loads the repository's Alembic `ScriptDirectory` and calls `get_current_head()`.

- [ ] **Step 4: Implement bounded database readiness**

Use a short-lived connection, `SELECT 1`, and dialect-appropriate statement timeout. For PostgreSQL, execute `SET LOCAL statement_timeout = 2000` inside the connection transaction. Map failures to the stable categories from the spec and log with `exc_info=True` only to the protected server logger.

- [ ] **Step 5: Replace the old health schema**

Define:

```python
class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str

class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["connected", "unavailable"]
    schema: Literal["current", "outdated", "unknown"]
    version: str
```

Remove the timestamp and environment fields from public health responses.

- [ ] **Step 6: Run the focused service and schema tests**

Run: `.venv/bin/python -m pytest tests/test_readiness_service.py tests/test_schemas.py -v`

Expected: PASS with no secret value in captured output.

- [ ] **Step 7: Commit the readiness service**

```bash
git add services/readiness_service.py schemas/common.py schemas/__init__.py tests/test_readiness_service.py tests/test_schemas.py
git commit -m "feat: add truthful database readiness service"
```

---

### Task 3: Wire fail-fast startup and health endpoints

**Files:**
- Modify: `app.py:44-53,322-330,339-343`
- Create: `tests/test_runtime_startup_and_health.py`
- Modify: `tests/test_api_v1.py:17-23`
- Test: `tests/test_runtime_startup_and_health.py`

**Interfaces:**
- Consumes: `check_database_readiness()`, `LivenessResponse`, `ReadinessResponse` from Task 2.
- Produces: `GET /health/live`, `GET /health/ready`, compatibility `GET /health`, and fail-fast lifespan startup.

- [ ] **Step 1: Write failing API tests for probe semantics**

```python
def test_liveness_never_calls_readiness(client, monkeypatch):
    monkeypatch.setattr(app, "check_database_readiness", Mock(side_effect=AssertionError))
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_readiness_returns_503_when_database_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(app, "check_database_readiness", lambda: unavailable_result())
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert response.headers["cache-control"] == "no-store"
```

Add a test proving `/health` calls the same handler semantics and a lifespan test proving an unavailable readiness result raises before `yield` in production. Add a test proving test-mode fixtures may start without an Alembic revision while `/health/ready` still reports their real state.

- [ ] **Step 2: Run the tests to demonstrate current false health behavior**

Run: `.venv/bin/python -m pytest tests/test_runtime_startup_and_health.py tests/test_api_v1.py -v`

Expected: FAIL because the new endpoints do not exist and `/health` is unconditional.

- [ ] **Step 3: Replace lifespan database initialization with verification**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_security_config()
    result = check_database_readiness()
    if settings.ENVIRONMENT.lower() == "production" and not result.ready:
        raise RuntimeError(f"Startup readiness failed: {result.failure_category}")
    yield
```

Do not catch the production `RuntimeError`. Do not call `init_db()`. In development/test, retain the result in `app.state.startup_readiness` and log its stable category; readiness remains `503` until the dependency is actually ready.

- [ ] **Step 4: Add liveness/readiness handlers**

Implement one private `_readiness_response()` helper used by both `/health/ready` and `/health`. Return `JSONResponse(status_code=503, ...)` for unavailable state and attach `Cache-Control: no-store` to both success and failure.

- [ ] **Step 5: Remove the runtime database-init API**

Delete `POST /database/init` and its now-unused `init_db` import from `app.py`. Update operator/API tests to assert the route is absent rather than authenticated.

- [ ] **Step 6: Run runtime and security tests**

Run: `.venv/bin/python -m pytest tests/test_runtime_startup_and_health.py tests/test_api_v1.py tests/test_spec08_admin_security.py -v`

Expected: PASS; health is truthful and operator security behavior is unchanged.

- [ ] **Step 7: Commit startup and probe wiring**

```bash
git add app.py tests/test_runtime_startup_and_health.py tests/test_api_v1.py tests/test_spec08_admin_security.py
git commit -m "fix: fail startup when database is not ready"
```

---

### Task 4: Correct environment validation and examples

**Files:**
- Modify: `config.py:67-100`
- Modify: `.env.example`
- Create: `.env.production.example`
- Create: `tests/test_environment_examples.py`
- Modify: `tests/test_spec08_admin_security.py:54-83`
- Test: `tests/test_environment_examples.py`

**Interfaces:**
- Consumes: `Settings.validate_security_config()`.
- Produces: `Settings.validate_runtime_config() -> None`, runnable development example, deliberately non-runnable production template.

- [ ] **Step 1: Write failing tests that load both example files**

```python
def test_development_example_is_startable():
    settings = Settings(_env_file=".env.example")
    settings.validate_runtime_config()
    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is True

def test_production_example_rejects_placeholders():
    settings = Settings(_env_file=".env.production.example")
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime_config()
```

Add cases for SQLite production, wildcard CORS, malformed origin JSON, disabled auth, and short admin keys.

- [ ] **Step 2: Run the tests and capture the current example failure**

Run: `.venv/bin/python -m pytest tests/test_environment_examples.py tests/test_spec08_admin_security.py -v`

Expected: FAIL because the examples and validator do not meet the spec.

- [ ] **Step 3: Implement runtime validation**

Keep `validate_security_config()` as a compatibility wrapper that calls `validate_runtime_config()`. In production, reject placeholder values by exact known prefixes (`replace_`, `replace-`, `your_`, `your-`) after trimming. Parse `CORS_ORIGINS` once through a shared method returning `list[str]`; reject `*` and non-HTTP(S) origins.

- [ ] **Step 4: Rewrite `.env.example` and add `.env.production.example`**

Use the exact values and comments in spec §4. Never place a working credential in either file.

- [ ] **Step 5: Run configuration tests**

Run: `.venv/bin/python -m pytest tests/test_environment_examples.py tests/test_spec08_admin_security.py -v`

Expected: PASS; no test prints secret settings.

- [ ] **Step 6: Commit configuration corrections**

```bash
git add config.py .env.example .env.production.example tests/test_environment_examples.py tests/test_spec08_admin_security.py
git commit -m "fix: provide valid development and production config templates"
```

---

### Task 5: Remove ambiguous unversioned job APIs

**Files:**
- Modify: `app.py:422-458`
- Create: `tests/test_route_ownership.py`
- Modify: `tests/test_api_routing_fix.py`
- Test: `tests/test_route_ownership.py`

**Interfaces:**
- Consumes: existing SPA handler `public_app`, versioned router in `api/v1/jobs.py`.
- Produces: unique `(method, path)` ownership and canonical `/api/v1/jobs` JSON contract.

- [ ] **Step 1: Write a failing duplicate-route guard**

```python
def test_no_duplicate_method_path_pairs():
    pairs = []
    for route in app.routes:
        path = getattr(route, "path", None)
        for method in getattr(route, "methods", set()):
            if path and method not in {"HEAD", "OPTIONS"}:
                pairs.append((method, path))
    duplicates = [pair for pair, count in Counter(pairs).items() if count > 1]
    assert duplicates == []
```

Also assert `/jobs` returns HTML, `/api/v1/jobs` returns JSON, and unversioned `/jobs/1` plus `/jobs/export` are not present in OpenAPI.

- [ ] **Step 2: Run the guard and verify `/jobs` is duplicated**

Run: `.venv/bin/python -m pytest tests/test_route_ownership.py -v`

Expected: FAIL showing duplicate `('GET', '/jobs')`.

- [ ] **Step 3: Delete legacy job list/detail/export handlers**

Remove `legacy_jobs`, `legacy_get_job`, and `legacy_export_jobs` plus imports used only by those handlers. Do not change `api/v1/jobs.py`.

- [ ] **Step 4: Make client-side route behavior explicit**

Keep `/jobs` in `public_app`. Do not add an unconstrained `/{path:path}` catch-all. If tests require `/jobs/<client-route>`, enumerate that route separately rather than allowing the SPA to swallow `/api/*`.

- [ ] **Step 5: Run routing and frontend contract tests**

Run: `.venv/bin/python -m pytest tests/test_route_ownership.py tests/test_api_routing_fix.py tests/test_api_smoke_and_contracts.py -v`

Expected: PASS; exactly one `/jobs` route exists and versioned APIs return JSON.

- [ ] **Step 6: Commit route cleanup**

```bash
git add app.py tests/test_route_ownership.py tests/test_api_routing_fix.py tests/test_api_smoke_and_contracts.py
git commit -m "fix: give public and API job routes unique ownership"
```

---

### Task 6: Update deployment probes and operator documentation

**Files:**
- Modify: `docker-compose.yml:64-76`
- Modify: `README.md`
- Modify: `Dockerfile` only if its startup command bypasses `docker/entrypoint.sh`
- Create: `tests/test_runtime_documentation.py`
- Test: `tests/test_runtime_documentation.py`

**Interfaces:**
- Consumes: probe paths from Task 3 and environment files from Task 4.
- Produces: accurate local startup, production startup, test, and health-check documentation.

- [ ] **Step 1: Write failing static deployment/documentation tests**

```python
def test_compose_uses_readiness_probe():
    compose = Path("docker-compose.yml").read_text()
    assert "http://127.0.0.1:8080/health/ready" in compose

def test_readme_runs_migrations_before_uvicorn():
    readme = Path("README.md").read_text()
    assert "alembic upgrade head" in readme
    assert "108 passed" not in readme
    assert "215_Passing" not in readme
```

- [ ] **Step 2: Run documentation tests and verify stale instructions fail**

Run: `.venv/bin/python -m pytest tests/test_runtime_documentation.py -v`

Expected: FAIL on the old health path and stale test totals.

- [ ] **Step 3: Update Compose and README**

Change the API health check to `/health/ready`. Document `/health/live` versus `/health/ready`, include `alembic upgrade head` before local startup, link both environment examples, and describe PostgreSQL as required for pgvector production verification. Replace hard-coded test totals with commands and CI status.

- [ ] **Step 4: Run the complete verification suite**

Run:

```bash
.venv/bin/python -m pytest -q
for f in tests/*.test.js; do node --test "$f"; done
docker compose config --quiet
git diff --check
```

Expected: all Python and JavaScript tests pass, Compose validates, and the diff has no whitespace errors.

- [ ] **Step 5: Commit deployment and documentation updates**

```bash
git add docker-compose.yml README.md Dockerfile tests/test_runtime_documentation.py
git commit -m "docs: align startup and probes with runtime readiness"
```
