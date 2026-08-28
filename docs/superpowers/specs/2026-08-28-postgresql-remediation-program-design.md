# SkillPulse PostgreSQL Remediation Program

**Status:** Approved design; implementation not started

**Date:** 2026-08-28

**Target:** FastAPI, PostgreSQL 16, pgvector, Redis, and the existing static frontend
**Supersedes:** PostgreSQL-specific production claims in `README.md` where they conflict with current behavior

## 1. Purpose

Bring the current PostgreSQL application into line with its documented production behavior. The program resolves six verified findings:

1. readiness reports database connectivity without checking it;
2. hybrid search does not use PostgreSQL full-text search or pgvector indexes;
3. candidate matching scores an unordered maximum of 200 jobs;
4. public and operator rate limits are process-local and trust unverified forwarding headers;
5. the documented environment quickstart fails its own production security validation;
6. `/jobs` is registered as both the public application route and a legacy JSON route.

The program improves the existing deployment. It does not depend on the separate Cloudflare Workers, D1, or Vectorize migration described in `docs/05_api_routing_fix_spec.md`.

## 2. Specification set

This program is implemented through three independently reviewable specifications:

- [`2026-08-28-runtime-readiness-and-routing-design.md`](2026-08-28-runtime-readiness-and-routing-design.md) — startup, readiness, configuration, documentation, and route ownership.
- [`2026-08-28-postgresql-retrieval-and-matching-design.md`](2026-08-28-postgresql-retrieval-and-matching-design.md) — indexed lexical/vector retrieval, bounded RRF, deterministic candidate matching, and backfills.
- [`2026-08-28-distributed-rate-limiting-design.md`](2026-08-28-distributed-rate-limiting-design.md) — Redis-backed enforcement, trusted-proxy identity, failure policy, and observability.

## 3. Program-wide decisions

### 3.1 PostgreSQL is authoritative

PostgreSQL 16 is the production relational and vector store. Alembic owns the production schema. Application worker startup must not call `Base.metadata.create_all()` or issue opportunistic `ALTER TABLE` statements.

SQLite remains permitted for fast unit tests and local experimentation. A feature is not production-verified until it has a PostgreSQL integration test covering the database-specific behavior it introduces.

### 3.2 Truthful behavior outranks graceful-looking output

The application must not claim that a database is connected, semantic retrieval ran, a job was evaluated, or a request was rate-limited unless that event actually occurred. When an essential dependency is unavailable, return an explicit unavailable response instead of substituting a fabricated score, neutral similarity, pseudo-semantic production embedding, or successful health status.

### 3.3 Backward compatibility

The versioned `/api/v1/*` contracts are canonical. The public browser routes remain `/`, `/match`, `/jobs`, `/market`, `/how-it-works`, `/about`, and `/dashboard`.

Unversioned JSON aliases may be removed when they collide with the public application or duplicate a versioned endpoint. Their removal is documented in the release notes; no redirect may convert an API request into an HTML `200` response.

### 3.4 Bounded request work

Public search and matching requests must have explicit upper bounds. No request may load every eligible job, create or repair every job embedding, scan unbounded Redis keys, or perform schema mutation.

## 4. Delivery order

### Phase 1 — Runtime reliability and route ownership

Ship database-backed readiness, fail-fast startup verification, corrected environment examples, and canonical route ownership first. This makes deployment state trustworthy before retrieval changes are introduced.

### Phase 2 — Indexed retrieval and deterministic matching

Apply the PostgreSQL search-document and embedding-metadata migration, backfill existing jobs, verify index use, then switch the search and matcher request paths. Phase 2 must not be enabled until backfill verification passes.

### Phase 3 — Distributed rate limiting

Enable Redis-backed limits after trusted-proxy configuration and Redis availability are verified in the target environment. Remove the old in-process stores in the same release; dual enforcement would produce confusing limits.

## 5. Cross-spec quality gates

Every phase must satisfy all applicable gates before release:

- focused tests demonstrate the old defect and the new behavior;
- the complete Python and JavaScript suites pass;
- PostgreSQL-specific tests run against PostgreSQL 16 with pgvector installed;
- public API errors remain JSON and do not redirect to the SPA;
- structured logs contain request IDs and dependency outcomes but no résumé text, credentials, raw session tokens, or unhashed client IP addresses;
- Alembic upgrade and downgrade paths are exercised on a disposable database;
- deployment configuration is validated before traffic is shifted;
- rollback does not require deleting collected jobs or candidate data.

## 6. Completion criteria

The remediation program is complete only when all of the following are true:

- database loss causes readiness to return `503` and prevents new traffic;
- production starts only against the expected Alembic revision;
- `EXPLAIN` confirms GIN and HNSW-assisted retrieval for representative datasets;
- hybrid search performs bounded database retrieval and never embeds jobs on the request path;
- a best match inserted after row 200 can still rank first;
- rate limits are shared across workers and cannot be bypassed with untrusted forwarding headers;
- copying the development example supports the documented local startup, while the production example refuses placeholder secrets;
- `/jobs` has one owner: the public application; job JSON is served only from `/api/v1/jobs`;
- README architecture and test instructions describe the implementation that actually ships.

## 7. Explicit non-goals

- Migrating to Cloudflare D1 or Vectorize.
- Replacing FastAPI, SQLAlchemy, Celery, Redis, or the vanilla frontend.
- Redesigning the public interface.
- Changing the 50/20/30 candidate fit formula.
- Adding user accounts or public persistence of candidate résumés.
- Reworking ingestion providers except where they must persist search documents and embedding metadata consistently.
