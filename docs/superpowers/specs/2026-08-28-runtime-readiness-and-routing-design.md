# Runtime Readiness, Configuration, and Routing Design

**Status:** Approved design; implementation not started

**Date:** 2026-08-28

**Program:** [`2026-08-28-postgresql-remediation-program-design.md`](2026-08-28-postgresql-remediation-program-design.md)
**Priority:** Phase 1

## 1. Purpose

Make process health, database readiness, startup configuration, and URL ownership unambiguous. This specification resolves false database health, swallowed startup failures, the unusable example environment, and the duplicate `/jobs` route.

## 2. Current failure modes

- `app.py` catches `init_db()` exceptions during lifespan startup and continues serving.
- `/health` always returns `database="connected"` without opening a connection.
- the container health check calls `/health`, so orchestration can mark a broken instance healthy.
- `.env.example` selects production but omits a valid `ADMIN_API_KEY` and leaves the default `DEBUG=True`; copying it triggers a production configuration refusal.
- `GET /jobs` is registered first as the SPA and later as a JSON compatibility endpoint; FastAPI resolves the first matching route, making the latter unreachable.
- production schema ownership is split between Alembic, `create_all()`, and runtime `ALTER TABLE` statements.
- the Alembic chain has never been applied: revision `0010`'s identifier exceeds the 32-character `alembic_version` column and no database carries an `alembic_version` row (program spec §3.1.1).

## 3. Selected runtime architecture

### 3.1 Liveness

`GET /health/live` answers only whether the ASGI process can serve a request.

- It performs no database, Redis, AI-provider, or network call.
- A healthy process returns HTTP `200` with:

```json
{
  "status": "ok",
  "service": "SkillPulse",
  "version": "1.0.0"
}
```

- The endpoint must remain fast enough for a one-second probe timeout.

### 3.2 Readiness

`GET /health/ready` determines whether the instance may receive application traffic.

- It executes `SELECT 1` through a short-lived SQLAlchemy connection.
- It verifies that the database's Alembic revision (`MigrationContext.get_current_revision()`) equals the application's expected head revision (`ScriptDirectory.from_config(...).get_current_head()` over the `migrations/` chain — not a hard-coded string). Revision identifiers stay ≤ 32 characters so the comparison and `alembic_version` stamping both work on PostgreSQL (see program spec §3.1.1).
- The total readiness check has a two-second deadline.
- Success returns HTTP `200`:

```json
{
  "status": "ready",
  "database": "connected",
  "schema": "current",
  "version": "1.0.0"
}
```

- Connection failure, timeout, missing `alembic_version`, or revision mismatch returns HTTP `503`:

```json
{
  "status": "not_ready",
  "database": "unavailable",
  "schema": "unknown",
  "version": "1.0.0"
}
```

The wire field is named `schema`. Because `schema` shadows a Pydantic `BaseModel` attribute, the response model declares the attribute as `schema_state` with `serialization_alias="schema"` (and populate-by-name enabled); the emitted JSON key is exactly `schema`.

The public response does not expose hostnames, credentials, SQL exception text, or migration identifiers. The server log records a structured error with the request ID and internal failure category.

`GET /health` remains as a compatibility alias for readiness and uses the same implementation and status code. This preserves existing deployment checks while correcting their semantics.

### 3.3 Startup verification

Production startup follows this sequence:

1. validate security and environment settings;
2. connect to PostgreSQL;
3. verify the Alembic revision is current;
4. start accepting traffic.

Failure in any step raises an exception and terminates the worker. The application must not catch and demote these failures to warnings.

The container entrypoint remains responsible for `alembic upgrade head` before Uvicorn starts. App workers verify schema state but never run migrations. This avoids concurrent DDL when multiple workers start.

`init_db()` is removed from application startup and from the production API surface. `Base.metadata.create_all()` remains available only to isolated test fixtures. Every table and column used in production—including admin sessions, extraction cache, source fields, and indexes—must exist in the Alembic chain.

Because the current schema was materialized by `create_all()` and never stamped (program spec §3.1.1), revision `0011_runtime_schema_authority` is inspect-guarded: it creates each object only when absent and, for the pre-existing nullable `jobs.source` / `jobs_posts.source` columns, backfills `NULL → 'gupy'` and issues `ALTER COLUMN … SET NOT NULL` plus the server default rather than failing. Operators of a pre-existing database run `alembic stamp 0010_pgvector_taxonomies` once before the first `alembic upgrade head`.

When a production worker's startup readiness check raises, it must exit non-zero (not demote to a warning, and not allow Uvicorn to silently respawn a still-broken worker). Container acceptance (§7.3) verifies the process actually terminates.

### 3.4 Probe configuration

- Docker Compose uses `/health/ready` for its API health check.
- A production orchestrator uses `/health/live` for process restart decisions and `/health/ready` for traffic admission.
- Probe requests are exempt from public rate limits.
- Readiness is not cached by browsers, proxies, or CDNs: responses include `Cache-Control: no-store`.

## 4. Environment configuration

### 4.1 Development example

`.env.example` is explicitly development-safe:

```dotenv
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=sqlite:///jobs.db
PORT=8000
HOST=0.0.0.0
ADMIN_AUTH_ENABLED=true
ADMIN_API_KEY=
RATE_LIMIT_ENABLED=false
# REDIS_URL=redis://localhost:6379/0   # required if RATE_LIMIT_ENABLED=true or Celery is used
```

An empty development admin key leaves the operator console unavailable but does not prevent the public application from starting. `RATE_LIMIT_ENABLED=false` is the documented dev default (the distributed rate-limit phase requires Redis). Any code that reads `REDIS_URL` tolerates it being unset in development. The file documents that a local operator key must be supplied explicitly and must not be committed.

The README local sequence becomes:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app:app --reload --port 8000
```

If SQLite remains in the quickstart, every migration and application model required by the public flows must continue to support SQLite. PostgreSQL is still required for pgvector integration and production verification.

### 4.2 Production example

Add `.env.production.example` with safe placeholders and secure defaults:

```dotenv
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://replace_user:replace_password@replace_host:5432/replace_database
REDIS_URL=redis://replace_host:6379/0
ADMIN_AUTH_ENABLED=true
ADMIN_API_KEY=replace-with-at-least-32-random-characters
PORT=8080
HOST=0.0.0.0
CORS_ORIGINS=["https://replace-with-public-origin.example"]
```

Placeholders are intentionally not runnable production credentials. Startup validation must reject the placeholder admin key and placeholder database URL with a clear configuration-category error.

### 4.3 Configuration validation

Production validation occurs before any listener accepts traffic and rejects:

- debug mode;
- disabled admin authentication;
- missing, placeholder, or shorter-than-32-character admin keys;
- SQLite database URLs;
- missing Redis configuration once the distributed rate-limit phase is enabled;
- wildcard CORS origins;
- malformed URLs and malformed JSON origin lists.

`REDIS_URL` changes from a hard-coded default (`redis://localhost:6379/0`) to `Optional[str] = None` so that "missing Redis configuration" is representable. Docker Compose and the environment examples set it explicitly. Where practical, the rate-limit phase also performs a bounded reachability check rather than trusting mere presence.

Validation messages name the setting but never print its secret value.

## 5. Route ownership

### 5.1 Public application

`GET /jobs` belongs exclusively to the public SPA. It returns `frontend/index.html` with an HTML content type.

### 5.2 Job APIs

The canonical job endpoints are:

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{id}`
- `GET /api/v1/jobs/export`
- `GET /api/v1/jobs/posts`
- `GET /api/v1/jobs/posts/{id}`
- `GET /api/v1/jobs/posts/export`
- `POST /api/v1/jobs/search/hybrid`

Remove the unversioned JSON handlers `GET /jobs`, `GET /jobs/{id}`, and `GET /jobs/export`. Requests to unknown browser paths beneath `/jobs/` return the SPA only if the public router deliberately supports that client-side route; they must never fall through to an integer API parameter or return JSON validation errors accidentally.

Other legacy aliases are outside this specification unless they create the same collision. Their eventual removal should follow a separately reviewed deprecation inventory.

### 5.3 Route regression guard

Add a test that builds a map of `(HTTP method, path)` for application routes and fails when two routes own the same pair, excluding deliberate aliases that share the same handler. The test must specifically prove:

- one `GET /jobs` route exists;
- `/jobs` returns HTML;
- `/api/v1/jobs` returns JSON;
- `/api/v1/jobs` cannot be swallowed by an SPA fallback;
- removed unversioned API aliases are absent from OpenAPI.

## 6. Error handling and observability

Startup and readiness logs use stable categories:

- `database_connection_failed`
- `database_readiness_timeout`
- `database_schema_missing`
- `database_schema_outdated`
- `configuration_invalid`

Each event includes environment, application version, and request ID when a request exists. Logs exclude database URLs and exception representations that may contain credentials.

## 7. Tests and acceptance criteria

### 7.1 Test harness

The default test database is built by running `alembic upgrade head` against a disposable SQLite file, not by `Base.metadata.create_all()`. This keeps `/health/ready` honest in the suite (an `alembic_version` row exists at the expected head) and exercises the migration chain on every run. `create_all()` is used only by narrowly scoped fixtures that explicitly assert test-mode behavior without a revision.

Every existing assertion that `GET /health` returns `200` with `database == "connected"` is updated to the readiness semantics of §3.2. Known call sites at time of writing: `tests/test_api_v1.py::test_health_endpoint`, `tests/test_spec08_admin_security.py::test_public_routes_remain_accessible`. The implementation plan re-greps for `"/health"` across `tests/` and the JS suites and updates each.

### 7.2 Unit and API tests

- Liveness returns `200` without calling the database.
- Readiness returns `200` only after `SELECT 1` and schema revision checks succeed.
- Connection error, timeout, absent revision table, and stale revision each return `503`.
- `/health` and `/health/ready` produce the same status and body semantics.
- readiness responses use `Cache-Control: no-store`.
- the readiness response serializes the key `schema` (not `schema_state`).
- production configuration rejects every invalid condition in §4.3.
- development configuration starts with the documented `.env.example`.
- the route regression guard in §5.3 passes.

### 7.3 Container acceptance

- With PostgreSQL running and migrated, the API container becomes ready.
- With PostgreSQL stopped, liveness remains `200` while readiness becomes `503`.
- A fresh container with an outdated schema fails and the process exits non-zero before Uvicorn receives traffic (verified by container exit status, not only by a coroutine raising).
- `alembic upgrade head` followed by restart restores readiness.
- `alembic upgrade head` succeeds against PostgreSQL 16 both from an empty database and from a `create_all()`-materialized database stamped at `0010_pgvector_taxonomies`.

### 7.4 Documentation acceptance

- README no longer contains conflicting exact test totals in multiple sections.
- The test badge, if retained, is generated by CI or describes the current verified total from one source.
- README distinguishes SQLite quickstart behavior from PostgreSQL production and pgvector integration tests.
- README does not claim `/health` confirms connectivity unless the real query is enabled.

## 8. Rollout and rollback

1. Rename revision `0010` to `0010_pgvector_taxonomies` (≤ 32 chars); land inspect-guarded `0011_runtime_schema_authority` with a complete `downgrade()`; verify upgrade/downgrade on a disposable PostgreSQL database from both an empty start and a stamped `create_all` start.
2. Deploy the new endpoints while `/health` still aliases readiness.
3. Update container and infrastructure probes.
4. Remove runtime schema mutation and duplicate routes.
5. Confirm a database outage removes the instance from service.

Rollback restores the previous application image but does not downgrade schema unless the migration itself caused the failure. Added health endpoints and additive migration records are safe to leave in place.
