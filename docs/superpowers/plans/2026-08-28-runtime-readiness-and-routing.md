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
- Rename: `migrations/versions/0010_upgrade_pgvector_taxonomies_multiregion.py` → `migrations/versions/0010_pgvector_taxonomies.py` (and its `revision` / docstring)
- Create: `migrations/versions/0011_runtime_schema_authority.py`
- Create: `tests/test_runtime_schema_migration.py`
- Create: `tests/fixtures/legacy_create_all_schema.py` (builds a `create_all()` DB for reconciliation tests)
- Modify: `database.py:78-108`
- Test: `tests/test_runtime_schema_migration.py`

**Interfaces:**
- Consumes: SQLAlchemy `Base.metadata`, renamed head `0010_pgvector_taxonomies`.
- Produces: Alembic revision `0011_runtime_schema_authority` (inspect-guarded, full `downgrade()`); test-only `create_test_schema()` behavior remains in `tests/conftest.py`.

- [ ] **Step 0: Rename revision `0010` to fit the 32-char `alembic_version` column**

`revision = "0010_pgvector_taxonomies"` (24 chars). Update the `Revision ID:` docstring line and the filename. Grep confirms nothing else references the old id. This is safe: no `alembic_version` row exists anywhere (verified — local `jobs.db` has no such table). Add `tests/test_runtime_schema_migration.py::test_all_revision_ids_fit_alembic_version_column` asserting every `revision`/`down_revision` string in `migrations/versions/` is ≤ 32 characters.

- [ ] **Step 1: Write a failing migration inventory + reconciliation test**

```python
def test_runtime_schema_revision_declares_missing_runtime_objects():
    migration = importlib.import_module(
        "migrations.versions.0011_runtime_schema_authority"
    )
    source = inspect.getsource(migration.upgrade)
    assert migration.down_revision == "0010_pgvector_taxonomies"
    assert "admin_sessions" in source
    assert "llm_extractions" in source
    assert "source" in source

def test_0011_reconciles_a_create_all_database(pg_or_sqlite_engine):
    # Build the schema the way the retired lifespan did: create_all() + a
    # NULLABLE jobs.source column, and NO alembic_version row.
    build_legacy_create_all_schema(pg_or_sqlite_engine)
    alembic_stamp(pg_or_sqlite_engine, "0010_pgvector_taxonomies")
    alembic_upgrade_head(pg_or_sqlite_engine)            # must NOT raise
    assert column_is_not_null(pg_or_sqlite_engine, "jobs", "source")
    assert table_exists(pg_or_sqlite_engine, "admin_sessions")
```

Also add a fresh-database acceptance test: empty DB → `alembic upgrade head` → `admin_sessions`, `llm_extractions`, and `source` (NOT NULL) on both `jobs` and `jobs_posts`; then `alembic downgrade 0010_pgvector_taxonomies` → those objects are gone; then `upgrade head` again succeeds.

- [ ] **Step 2: Run the focused test and verify the missing revision fails**

Run: `.venv/bin/python -m pytest tests/test_runtime_schema_migration.py -v`

Expected: FAIL because `0011_runtime_schema_authority` does not exist.

- [ ] **Step 3: Add revision `0011_runtime_schema_authority` (inspect-guarded, reconciling)**

```python
revision = "0011_runtime_schema_authority"
down_revision = "0010_pgvector_taxonomies"
```

Using SQLAlchemy `inspect()` at the top of `upgrade()`:

- `jobs.source` / `jobs_posts.source`:
  - if the column is **absent** → add `VARCHAR(50) NOT NULL DEFAULT 'gupy'` + `ix_jobs_source` / `ix_jobs_posts_source`.
  - if the column is **present but nullable** (the retired-lifespan case) → `UPDATE … SET source='gupy' WHERE source IS NULL`, then `ALTER COLUMN source SET NOT NULL` and `SET DEFAULT 'gupy'`, and create the index if absent.
  - if the column is present with an incompatible **type** → raise a clear error (this is genuinely unrecoverable and must not be silently masked).
- `admin_sessions`, `llm_extractions`, their unique/index constraints on `token_hash` / `fingerprint`: create only when `inspector.has_table(...)` is false; when present, assert the columns/nullability match the entity and raise only on a real mismatch.
- Never use `CREATE TABLE IF NOT EXISTS`; use the inspector.
- `downgrade()` drops `llm_extractions`, `admin_sessions`, the `source` indexes, and reverts `source` to nullable (does not drop it — data preservation), in reverse dependency order.

Document in the migration docstring: pre-existing `create_all` databases must be `alembic stamp 0010_pgvector_taxonomies`'d once before the first `alembic upgrade head`.

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
git add migrations/versions/ database.py tests/test_runtime_schema_migration.py tests/fixtures/legacy_create_all_schema.py
git commit -m "fix: make Alembic authoritative for runtime schema"
```

Note: `git add migrations/versions/` picks up both the renamed `0010_pgvector_taxonomies.py` and the deletion of the old filename.

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
    assert result.schema_state == "current"

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
    schema_state: Literal["current", "outdated", "unknown"]   # NOT `schema` — shadows BaseModel
    failure_category: str | None = None
    public_message: str | None = None
```

`get_current_revision(connection)` uses `MigrationContext.configure(connection).get_current_revision()`. `get_expected_head()` loads the repository's Alembic `ScriptDirectory` (from `migrations/`, per `alembic.ini`) and calls `get_current_head()` — no hard-coded revision string. Delete the stray top-level `alembic/` directory (empty `versions/`, `target_metadata = None`) so nothing resolves the wrong script location.

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
    model_config = ConfigDict(populate_by_name=True)
    status: Literal["ready", "not_ready"]
    database: Literal["connected", "unavailable"]
    schema_state: Literal["current", "outdated", "unknown"] = Field(serialization_alias="schema")
    version: str
```

The emitted JSON key is `schema` (matches runtime spec §3.2). Add a test asserting `response.json()` contains `"schema"` and not `"schema_state"`. Remove the timestamp and environment fields from public health responses.

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
- Modify: `tests/conftest.py` (build the test DB with `alembic upgrade head`, not `init_db()`)
- Create: `tests/test_runtime_startup_and_health.py`
- Modify: `tests/test_api_v1.py:14-20`
- Modify: `tests/test_spec08_admin_security.py` (the `/health` → 200 assertion in `test_public_routes_remain_accessible`)
- Test: `tests/test_runtime_startup_and_health.py`

**Interfaces:**
- Consumes: `check_database_readiness()`, `LivenessResponse`, `ReadinessResponse` from Task 2.
- Produces: `GET /health/live`, `GET /health/ready`, compatibility `GET /health`, and fail-fast lifespan startup.

- [ ] **Step 0: Make the test database Alembic-managed**

In `tests/conftest.py`, replace the `init_db()` call in `setup_test_database` with `subprocess`-run `alembic upgrade head` (or `command.upgrade(config, "head")`) against the disposable `test_jobs.db`, so `/health/ready` sees a real `alembic_version` at head. Keep a separate opt-in fixture that uses `Base.metadata.create_all()` for the specific tests that assert test-mode-without-revision behavior. Re-grep `tests/` and `tests/*.test.js` for `"/health"` and fix every assertion that expects `200`/`database=="connected"` from the unconditional handler.

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

The `RuntimeError` must reach the ASGI server so the process exits non-zero. Verify in Task 6 Step 4 / §7.3 with an actual container run (`docker compose up` against a stale/absent schema, assert the `api` container exits non-zero) — not only a unit test that the coroutine raises.

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
    # Map (method, path) -> set of endpoint callables. A pair owned by two
    # *different* handlers is the bug. Spec §5.3 excludes deliberate aliases
    # that resolve to the same handler (e.g. /health and /health/ready
    # sharing one _readiness_response()).
    owners: dict[tuple[str, str], set] = defaultdict(set)
    for route in app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        for method in getattr(route, "methods", set()):
            if path and method not in {"HEAD", "OPTIONS"}:
                owners[(method, path)].add(endpoint)
    conflicts = {pair: fns for pair, fns in owners.items() if len(fns) > 1}
    assert conflicts == {}
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
