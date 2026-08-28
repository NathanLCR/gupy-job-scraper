# PostgreSQL Retrieval and Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace full-dataset in-memory ranking and unordered matcher truncation with bounded PostgreSQL GIN/HNSW retrieval and deterministic exact scoring.

**Architecture:** PostgreSQL maintains a weighted search document and embedding provenance for every job. A focused retrieval repository runs bounded dense and lexical branches, fuses only returned ranks with RRF, and loads full ORM entities after IDs are selected. Candidate matching reuses that repository to select at most 300 deterministic candidates before applying the unchanged 50/20/30 score.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2, PostgreSQL 16, pgvector, PostgreSQL full-text search, Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-postgresql-retrieval-and-matching-design.md`

## Global Constraints

- Execute this plan after `0011_runtime_schema_authority` from the runtime plan.
- Production compares only embeddings produced by the configured `ACTIVE_EMBEDDING_MODEL`.
- Public requests generate one query/candidate embedding and zero job embeddings.
- Each dense or lexical branch returns `min(500, max(100, top_k * 5))` rows; matching uses 200 per branch and evaluates at most 300 unique jobs.
- Missing/incompatible job embeddings contribute zero semantic points, never a neutral 0.5 similarity.
- PostgreSQL-specific behavior requires PostgreSQL integration tests; SQLite unit tests do not prove index use.
- Preserve existing response fields; new count/mode fields are additive and optional branch scores are nullable.

---

### Task 1: Add search-document and embedding-provenance schema

**Files:**
- Create: `migrations/versions/0012_postgres_indexed_retrieval.py`
- Modify: `entities/job.py:1-107`
- Create: `tests/test_postgres_retrieval_migration.py`
- Test: `tests/test_postgres_retrieval_migration.py`

**Interfaces:**
- Consumes: Alembic revision `0011_runtime_schema_authority`, `Job` relationships.
- Produces: `jobs.search_document`, `jobs.embedding_model`, `jobs.embedding_updated_at`, refresh function/triggers, GIN index, partial HNSW index.

- [ ] **Step 1: Write failing model and migration tests**

```python
def test_job_model_exposes_retrieval_metadata():
    assert "search_document" in Job.__table__.columns
    assert "embedding_model" in Job.__table__.columns
    assert "embedding_updated_at" in Job.__table__.columns

def test_retrieval_migration_follows_runtime_schema():
    migration = importlib.import_module(
        "migrations.versions.0012_postgres_indexed_retrieval"
    )
    assert migration.down_revision == "0011_runtime_schema_authority"
```

PostgreSQL integration assertions must inspect `pg_indexes`, `pg_proc`, and `pg_trigger` for the names defined below.

- [ ] **Step 2: Run the tests and verify the schema is absent**

Run: `.venv/bin/python -m pytest tests/test_postgres_retrieval_migration.py -v`

Expected: FAIL because revision `0012` and model columns do not exist.

- [ ] **Step 3: Extend the `Job` model with dialect-compatible fields**

```python
from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import TSVECTOR

search_document = mapped_column(
    TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
)
embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Do not serialize `search_document` in `to_dict()`. Add `embedding_model` and `embedding_updated_at` only if operator/debug schemas require them; public `JobResponse` must not expose raw vectors.

- [ ] **Step 4: Create revision `0012_postgres_indexed_retrieval`**

For PostgreSQL:

- add the three columns;
- create `refresh_job_search_document(target_job_id bigint)` using `setweight(to_tsvector('english', coalesce(...)), 'A'|'B'|'C'|'D')`;
- aggregate hard skills with `string_agg(DISTINCT hard_skills.name, ' ')`;
- aggregate tech stack with `jsonb_array_elements_text(coalesce(jobs.tech_stack::jsonb, '[]'::jsonb))`;
- create triggers with stable names `trg_jobs_refresh_search_document`, `trg_job_hard_skills_refresh_search_document`, `trg_hard_skills_refresh_search_document`, and `trg_companies_refresh_search_document`;
- create `ix_jobs_search_document_gin USING gin(search_document)`;
- replace `ix_jobs_embedding_hnsw` with a partial cosine HNSW index `WHERE embedding IS NOT NULL`.

For SQLite, add provenance columns and a text `search_document`; skip PostgreSQL functions, triggers, and indexes that SQLite cannot support.

- [ ] **Step 5: Implement precise trigger behavior**

The jobs trigger refreshes after insert or update of `job_title`, `tech_stack`, `description`, `seniority`, `company_id`, `city_id`, `state_id`, `region`, or `workplace_type`. The association trigger refreshes old and new job IDs. Company and hard-skill update triggers refresh only jobs referencing the changed row.

In the same jobs trigger path, changes to title, tech stack, description, seniority, or hard-skill associations set `embedding`, `embedding_model`, and `embedding_updated_at` to `NULL` before the search document refresh. A hard-skill name update performs the same invalidation for every associated job before refreshing its search document. Company-name updates refresh lexical documents without invalidating embeddings because company name is not part of `_format_job_text()`.

- [ ] **Step 6: Run migration upgrade/downgrade tests**

Run: `.venv/bin/python -m pytest tests/test_postgres_retrieval_migration.py tests/test_models.py -v`

Expected: PASS on SQLite model compatibility and the configured PostgreSQL integration database.

- [ ] **Step 7: Commit the retrieval schema**

```bash
git add migrations/versions/0012_postgres_indexed_retrieval.py entities/job.py tests/test_postgres_retrieval_migration.py
git commit -m "feat: add indexed PostgreSQL job search schema"
```

---

### Task 2: Enforce active embedding provenance

**Files:**
- Modify: `config.py:35-45,67-100`
- Modify: `services/embedding_service.py:21-204`
- Modify: `services/extractor_service.py:344-379`
- Create: `tests/test_embedding_provenance.py`
- Test: `tests/test_embedding_provenance.py`

**Interfaces:**
- Consumes: `Job.embedding_model`, `Job.embedding_updated_at` from Task 1.
- Produces: `settings.ACTIVE_EMBEDDING_MODEL`, `EmbeddingUnavailableError`, `embed_query(text: str) -> list[float]`, `embed_job_record(job: Job) -> tuple[list[float], str]`.

- [ ] **Step 1: Write failing provenance and production-fallback tests**

```python
def test_production_never_uses_hash_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(embedding, "_call_cloudflare_workers_ai", lambda text: None)
    monkeypatch.setattr(embedding, "_load_transformer_model", lambda: None)
    with pytest.raises(EmbeddingUnavailableError):
        embedding.embed_query("python backend")

def test_extractor_persists_embedding_model(test_db, monkeypatch):
    monkeypatch.setattr(settings, "ACTIVE_EMBEDDING_MODEL", "test-model-v1")
    # run one extraction write
    assert saved_job.embedding_model == "test-model-v1"
    assert saved_job.embedding_updated_at is not None
```

- [ ] **Step 2: Run the tests and verify fallback/provenance failures**

Run: `.venv/bin/python -m pytest tests/test_embedding_provenance.py -v`

Expected: FAIL because the exception, active model setting, and persisted provenance do not exist.

- [ ] **Step 3: Add explicit embedding configuration and exception**

```python
class EmbeddingUnavailableError(RuntimeError):
    pass

ACTIVE_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
```

`embed_query()` must enforce 384 dimensions and refuse deterministic fallback in production. Retain deterministic fallback only for `development` and `test`.

- [ ] **Step 4: Persist provenance when extraction creates a job**

When `_run_extractor()` assigns `embedding`, also set:

```python
embedding_model=settings.ACTIVE_EMBEDDING_MODEL
embedding_updated_at=datetime.now(UTC)
```

Generate the vector before constructing `Job`; if embedding is unavailable, roll back that job and log the stable category `job_embedding_unavailable` without description text.

- [ ] **Step 5: Run focused extraction and embedding tests**

Run: `.venv/bin/python -m pytest tests/test_embedding_provenance.py tests/test_extraction_cascade.py tests/test_cloudflare_and_caching.py -v`

Expected: PASS with deterministic fallback confined to non-production environments.

- [ ] **Step 6: Commit provenance enforcement**

```bash
git add config.py services/embedding_service.py services/extractor_service.py tests/test_embedding_provenance.py tests/test_extraction_cascade.py
git commit -m "fix: track and enforce active embedding model"
```

---

### Task 3: Build the bounded PostgreSQL retrieval repository

**Files:**
- Create: `services/postgres_retrieval_service.py`
- Create: `tests/test_postgres_retrieval_service.py`
- Test: `tests/test_postgres_retrieval_service.py`

**Interfaces:**
- Consumes: SQLAlchemy `Session`, `Job`, `embed_query()`, active embedding model.
- Produces: `RetrievalFilters`, `RankedCandidate`, `RetrievalResult`, `PostgresRetrievalService.retrieve()`.

- [ ] **Step 1: Write failing RRF and bounded-query tests**

```python
def test_rrf_omits_missing_branch():
    fused = fuse_ranked_ids(
        dense=[BranchHit(job_id=1, rank=1, score=.9)],
        sparse=[BranchHit(job_id=2, rank=1, score=3.0)],
        dense_weight=.5,
        sparse_weight=.5,
    )
    assert fused[0].dense_rank == 1
    assert fused[0].sparse_rank is None
    assert fused[1].dense_rank is None

def test_pool_size_is_bounded():
    assert candidate_pool_size(1) == 100
    assert candidate_pool_size(100) == 500
```

Add PostgreSQL tests that seed more than 500 jobs and assert each SQL branch returns no more than the requested pool.

- [ ] **Step 2: Run the tests and verify the repository is absent**

Run: `.venv/bin/python -m pytest tests/test_postgres_retrieval_service.py -v`

Expected: FAIL importing the new module.

- [ ] **Step 3: Define immutable repository types**

```python
@dataclass(frozen=True)
class RetrievalFilters:
    region: str | None = None
    country_code: str | None = None
    workplace_type: str | None = None
    seniority: str | None = None
    min_salary: int | None = None
    max_salary: int | None = None
    skill: str | None = None
    location: str | None = None

@dataclass(frozen=True)
class RankedCandidate:
    job_id: int
    rrf_score: float
    dense_rank: int | None
    dense_score: float | None
    sparse_rank: int | None
    sparse_score: float | None

@dataclass(frozen=True)
class RetrievalResult:
    candidates: tuple[RankedCandidate, ...]
    mode: Literal["hybrid", "dense", "lexical"]
```

- [ ] **Step 4: Implement filter and branch queries**

`_dense_hits()` uses `Job.embedding.cosine_distance(query_vector)`, filters `Job.embedding_model == settings.ACTIVE_EMBEDDING_MODEL`, orders by distance then ID, and limits the branch. `_sparse_hits()` uses `websearch_to_tsquery('english', bindparam('query'))`, `@@`, and `ts_rank_cd`, orders by score descending then ID, and limits the branch.

Build every filter with SQLAlchemy expressions. Do not use Python post-filtering or raw string interpolation.

- [ ] **Step 5: Implement deterministic RRF**

Normalize weights to one, reject zero total, apply `weight / (60 + rank)` only when a hit exists, and sort by RRF, dense score, sparse score, then job ID as specified. Set mode from non-empty contributing branches.

- [ ] **Step 6: Run algorithm and PostgreSQL repository tests**

Run: `.venv/bin/python -m pytest tests/test_postgres_retrieval_service.py -v`

Expected: PASS; query counters prove no full ORM materialization.

- [ ] **Step 7: Commit the retrieval repository**

```bash
git add services/postgres_retrieval_service.py tests/test_postgres_retrieval_service.py
git commit -m "feat: add bounded PostgreSQL hybrid retrieval"
```

---

### Task 4: Replace the public hybrid-search full scan

**Files:**
- Modify: `services/hybrid_search_service.py:1-238`
- Modify: `schemas/job.py:132-161`
- Modify: `api/v1/jobs.py:106-149`
- Modify: `tests/test_hybrid_search_and_matcher.py`
- Create: `tests/test_hybrid_search_postgres_contract.py`
- Test: `tests/test_hybrid_search_postgres_contract.py`

**Interfaces:**
- Consumes: `PostgresRetrievalService.retrieve()` from Task 3.
- Produces: bounded `hybrid_search_jobs()`, nullable branch fields, `HybridSearchResponse.retrieval_mode`.

- [ ] **Step 1: Write failing request/response and no-job-embedding tests**

```python
def test_hybrid_search_embeds_query_once_and_never_jobs(client, monkeypatch):
    query_embed = Mock(return_value=[0.1] * 384)
    monkeypatch.setattr(retrieval_module, "embed_query", query_embed)
    monkeypatch.setattr(embedding_module, "embed_job", Mock(side_effect=AssertionError))
    response = client.post("/api/v1/jobs/search/hybrid", json={"query": "python"})
    assert response.status_code == 200
    query_embed.assert_called_once()

def test_zero_total_weight_is_rejected(client):
    response = client.post(
        "/api/v1/jobs/search/hybrid",
        json={"query": "python", "dense_weight": 0, "sparse_weight": 0},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and observe current full-scan behavior**

Run: `.venv/bin/python -m pytest tests/test_hybrid_search_postgres_contract.py tests/test_hybrid_search_and_matcher.py -v`

Expected: FAIL because retrieval mode/null branch fields are absent and the old service embeds jobs.

- [ ] **Step 3: Update Pydantic contracts**

Make `dense_score`, `dense_rank`, `sparse_score`, and `sparse_rank` optional. Add:

```python
retrieval_mode: Literal["hybrid", "dense", "lexical"]
```

Add a model validator requiring `dense_weight + sparse_weight > 0` after bounds validation and trim/query non-whitespace validation.

- [ ] **Step 4: Reduce `hybrid_search_service.py` to orchestration**

Delete `_compute_sparse_text_score()` and all loops over `filtered_jobs`. Call the repository, load only selected job IDs with eager relationships, preserve fused order through an ID-position map, and return `HybridSearchResultItem` values with nullable branch fields.

Map `EmbeddingUnavailableError` to a service-level exception that `api/v1/jobs.py` returns as HTTP `503` with the standard request ID.

- [ ] **Step 5: Run public hybrid-search tests**

Run: `.venv/bin/python -m pytest tests/test_hybrid_search_postgres_contract.py tests/test_hybrid_search_and_matcher.py tests/test_api_smoke_and_contracts.py -v`

Expected: PASS; no request path calls `embed_job`.

- [ ] **Step 6: Commit the public search cutover**

```bash
git add services/hybrid_search_service.py schemas/job.py api/v1/jobs.py tests/test_hybrid_search_postgres_contract.py tests/test_hybrid_search_and_matcher.py tests/test_api_smoke_and_contracts.py
git commit -m "feat: use indexed PostgreSQL hybrid search"
```

---

### Task 5: Replace unordered matcher selection with bounded retrieval

**Files:**
- Modify: `services/matcher_service.py:151-337`
- Modify: `schemas/matcher.py:31-78`
- Modify: `frontend/script.js:215-228,430-535`
- Modify: `tests/test_hybrid_search_and_matcher.py`
- Create: `tests/test_matcher_candidate_selection.py`
- Modify: `tests/frontend_api_routing.test.js`
- Test: `tests/test_matcher_candidate_selection.py`

**Interfaces:**
- Consumes: `PostgresRetrievalService.retrieve()` with explicit 200-row branch sizes and 300-row union cap.
- Produces: deterministic match selection and precise `total_eligible`, `total_evaluated`, `total_qualified`, `total_matches` counts.

- [ ] **Step 1: Write a failing regression with the best job after row 200**

```python
def test_best_match_after_row_200_can_rank_first(postgres_db):
    seed_low_fit_jobs(postgres_db, count=200)
    best = seed_exact_python_fastapi_match(postgres_db)
    result = CandidateMatcherService.match_resume(RESUME, db=postgres_db, limit=10)
    assert result["matches"][0]["job_id"] == best.id
    assert result["total_eligible"] == 201
    assert result["total_evaluated"] <= 300
```

Add tests for missing embedding = zero vector points, stable job-ID tie breaking, and distinct count semantics.

- [ ] **Step 2: Run matcher regressions and verify the row-201 failure**

Run: `.venv/bin/python -m pytest tests/test_matcher_candidate_selection.py -v`

Expected: FAIL because unordered `LIMIT 200` excludes the best job.

- [ ] **Step 3: Build the stable lexical profile query**

Add a pure helper:

```python
def build_candidate_lexical_query(
    hard_skills: Sequence[str],
    tech_stack: Sequence[str],
    seniority: str | None,
) -> str:
```

Deduplicate case-insensitively, exclude soft skills and personal prose, order canonical labels, and join hard skills + remaining tech stack + supplied seniority.

- [ ] **Step 4: Retrieve and count candidates before exact scoring**

Issue a separate `COUNT(*)` under region/seniority filters for `total_eligible`. Retrieve 200 dense and 200 lexical hits, fuse/cap at 300, and load only those jobs. Remove `query.limit(200)`.

- [ ] **Step 5: Make exact scoring truthful**

Set `vec_sim = 0.0` when a job lacks an active-model vector. Use “Strong semantic similarity” only for measured similarity at least 70%; otherwise say “Semantic similarity measured at N%” or “Semantic evidence unavailable.” Sort `fit_score DESC, job_id ASC`.

- [ ] **Step 6: Add precise response counts and frontend validation**

Extend `CandidateMatchResponse` with `total_eligible` and `total_qualified`. Keep `total_evaluated` and `total_matches`; update `validateCandidateMatchResponse()` to require all four numeric fields without generating fallback values.

- [ ] **Step 7: Run matcher and frontend contract tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_matcher_candidate_selection.py tests/test_hybrid_search_and_matcher.py -v
node --test tests/frontend_api_routing.test.js
```

Expected: PASS; the row-201 job ranks first and malformed count responses are rejected.

- [ ] **Step 8: Commit matcher selection changes**

```bash
git add services/matcher_service.py schemas/matcher.py frontend/script.js tests/test_matcher_candidate_selection.py tests/test_hybrid_search_and_matcher.py tests/frontend_api_routing.test.js
git commit -m "fix: retrieve deterministic matcher candidate pool"
```

---

### Task 6: Add resumable search and embedding backfills

**Files:**
- Create: `scripts/backfill_search_documents.py`
- Create: `scripts/backfill_job_embeddings.py`
- Modify: `services/celery_app.py`
- Create: `tests/test_retrieval_backfills.py`
- Test: `tests/test_retrieval_backfills.py`

**Interfaces:**
- Consumes: PostgreSQL refresh function from Task 1, `get_embeddings_batch()` and active model from Task 2.
- Produces: `backfill_search_documents(batch_size: int = 500)`, `backfill_job_embeddings(batch_size: int = 100)`, optional Celery task wrappers.

- [ ] **Step 1: Write failing idempotence/resume tests**

```python
def test_search_backfill_resumes_after_last_id(postgres_db):
    first = backfill_search_documents(postgres_db, batch_size=2, max_batches=1)
    second = backfill_search_documents(postgres_db, batch_size=2)
    assert first.updated == 2
    assert second.updated == total_jobs - 2
    assert count_missing_search_documents(postgres_db) == 0

def test_embedding_backfill_skips_active_model_rows(postgres_db, monkeypatch):
    # one current, one stale, one missing
    result = backfill_job_embeddings(postgres_db, batch_size=100)
    assert result.updated == 2
```

- [ ] **Step 2: Run tests and verify scripts are absent**

Run: `.venv/bin/python -m pytest tests/test_retrieval_backfills.py -v`

Expected: FAIL importing both scripts.

- [ ] **Step 3: Implement bounded search-document backfill**

Select primary keys greater than the last committed ID, ordered ascending, limit 500, call `refresh_job_search_document(id)`, commit each batch, and emit aggregate counts. CLI flags are `--batch-size`, `--start-after-id`, and `--max-batches`.

- [ ] **Step 4: Implement bounded embedding backfill**

Select rows with null embedding or mismatched model, format texts with existing helpers, call `get_embeddings_batch()` with at most 100 texts, validate every dimension, and update vector + model + UTC timestamp in one transaction per batch. Retry transient provider errors at 2, 4, and 8 seconds; exit nonzero on authentication/configuration errors.

- [ ] **Step 5: Add Celery wrappers without moving core logic**

Expose `task_backfill_search_documents` and `task_backfill_job_embeddings` that call the script functions. Keep CLI/business logic importable and independently testable.

- [ ] **Step 6: Run backfill tests**

Run: `.venv/bin/python -m pytest tests/test_retrieval_backfills.py tests/test_extraction_cascade.py -v`

Expected: PASS; repeated runs perform no extra provider calls for current rows.

- [ ] **Step 7: Commit operational backfills**

```bash
git add scripts/backfill_search_documents.py scripts/backfill_job_embeddings.py services/celery_app.py tests/test_retrieval_backfills.py
git commit -m "feat: add resumable PostgreSQL retrieval backfills"
```

---

### Task 7: Add activation gates, query-plan checks, and release verification

**Files:**
- Modify: `config.py`
- Modify: `.env.production.example`
- Create: `tests/test_postgres_retrieval_acceptance.py`
- Modify: `README.md`
- Test: `tests/test_postgres_retrieval_acceptance.py`

**Interfaces:**
- Consumes: migrations/backfills/repository from Tasks 1-6.
- Produces: `POSTGRES_INDEXED_RETRIEVAL_ENABLED`, activation checks, explain-plan artifacts, accurate architecture documentation.

- [ ] **Step 1: Write failing activation-gate tests**

```python
def test_activation_requires_search_and_embedding_coverage(postgres_db):
    status = evaluate_retrieval_activation(postgres_db)
    assert status.search_document_coverage == 1.0
    assert status.embedding_coverage >= 0.95
    assert status.can_activate is True
```

Add failing cases for invalid indexes, stale schema, and embedding coverage below 95%.

- [ ] **Step 2: Implement activation status**

Create a small function in `services/postgres_retrieval_service.py` returning coverage ratios and index validity from PostgreSQL catalogs. When the feature flag is true at production startup, raise on failed activation status.

- [ ] **Step 3: Add representative query-plan acceptance tests**

Seed at least 10,000 jobs in a disposable PostgreSQL database, run `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, and assert plan nodes contain a GIN-assisted bitmap/index scan for selective lexical search and the HNSW index name for vector ordering. Record JSON plans under the test artifact directory, not in the repository.

Measure 30 warmed retrieval runs and 30 warmed exact-scoring runs separately. Assert p95 database retrieval excluding embedding-provider latency is below 300 ms and p95 scoring of a 300-job candidate pool is below 500 ms. Mark these as PostgreSQL performance tests so unit-only jobs can skip them explicitly rather than silently treating SQLite timing as equivalent.

- [ ] **Step 4: Update production config and README**

Document `ACTIVE_EMBEDDING_MODEL`, `POSTGRES_INDEXED_RETRIEVAL_ENABLED`, backfill commands, activation thresholds, and the real indexed architecture. Remove claims that search is database-native unless the flag and indexes are enabled.

- [ ] **Step 5: Run full verification**

Run:

```bash
.venv/bin/python -m pytest -q
for f in tests/*.test.js; do node --test "$f"; done
alembic upgrade head
alembic downgrade 0011_runtime_schema_authority
alembic upgrade head
git diff --check
```

Expected: all suites pass; PostgreSQL migration round-trip succeeds; no full-scan code remains in the enabled retrieval path.

- [ ] **Step 6: Commit activation and release documentation**

```bash
git add config.py .env.production.example services/postgres_retrieval_service.py tests/test_postgres_retrieval_acceptance.py README.md
git commit -m "docs: add indexed retrieval activation gates"
```
