# PostgreSQL Retrieval and Candidate Matching Design

**Status:** Approved design; implementation not started

**Date:** 2026-08-28

**Program:** [`2026-08-28-postgresql-remediation-program-design.md`](2026-08-28-postgresql-remediation-program-design.md)

**Priority:** Phase 2

**Database:** PostgreSQL 16 with pgvector

## 1. Purpose

Replace in-memory full-dataset ranking and arbitrary matcher truncation with bounded, indexed PostgreSQL retrieval. Preserve the existing RRF concept and 50/20/30 fit formula while making every reported result deterministic and truthful.

## 2. Current failure modes

- `hybrid_search_jobs()` materializes every filtered job with `db.scalars(stmt).all()`.
- dense similarity and lexical scoring run in Python for every candidate.
- a missing stored embedding may be generated during the public request, potentially causing one external AI call per job.
- the HNSW index and PostgreSQL full-text search are not used.
- every job receives both a dense and sparse rank, including zero-score lexical results, so a non-match still contributes to RRF.
- the matcher executes an unordered `LIMIT 200`; jobs outside that subset cannot match.
- missing vectors receive a neutral `0.5` similarity in some paths, manufacturing 15 semantic points.
- stored embeddings do not identify the model that created them, allowing incompatible vector spaces to be mixed.

## 3. Data model and migration

### 3.1 Job search document

Add a nullable PostgreSQL `tsvector` column named `search_document` to `jobs` and a GIN index named `ix_jobs_search_document_gin`.

The document applies these weights:

- weight `A`: job title and canonical hard-skill names;
- weight `B`: company name and tech-stack values;
- weight `C`: seniority, city, state, region, and workplace type;
- weight `D`: description.

Because the document includes related tables, it is maintained by a PostgreSQL function `refresh_job_search_document(target_job_id bigint)`. The function reads the job row plus its related rows and writes `jobs.search_document`; tech-stack tokens are extracted with a lateral `jsonb_array_elements_text(coalesce(jobs.tech_stack::jsonb, '[]'::jsonb))` aggregated into a single text value before `to_tsvector`. `AFTER` triggers invoke it after:

- insert or update of `job_title`, `tech_stack`, `description`, `seniority`, `company_id`, `city_id`, `state_id`, `region`, or `workplace_type` on `jobs`;
- insert or delete on `job_hard_skills`;
- hard-skill name update;
- company name update.

Company and hard-skill updates refresh only affected jobs. The migration backfills every existing job in bounded batches after the column, function, triggers, and GIN index are created (the GIN index is created on the empty column first and maintained incrementally by the backfill).

Embedding invalidation (§3.2) is a **separate `BEFORE INSERT OR UPDATE` trigger on `jobs`** that sets `NEW.embedding`, `NEW.embedding_model`, and `NEW.embedding_updated_at` to `NULL` when `job_title`, `tech_stack`, `description`, `seniority`, or the row's hard-skill associations changed. Doing this in a `BEFORE` trigger mutating `NEW` avoids a recursive self-`UPDATE`. For hard-skill association and hard-skill-name changes (which cannot see `jobs.NEW`), a guarded statement-level path performs the same nulling for the affected job IDs and must be protected against re-entry (`pg_trigger_depth() = 1`). Company-name changes refresh the lexical document but never null embeddings, because company name is not part of `_format_job_text()`.

Application write paths may call the same database function after a multi-table transaction, but PostgreSQL remains the consistency boundary. Search correctness must not depend on a particular Python service remembering to rebuild the document.

### 3.2 Embedding provenance

Add these columns to `jobs`:

- `embedding_model varchar(255) null`
- `embedding_updated_at timestamptz null`

An embedding is eligible for dense retrieval only when:

- it is non-null and exactly 384 dimensions;
- `embedding_model` equals the configured active production model identifier;
- the row is not awaiting re-embedding after a search-relevant content change.

Search-relevant job changes clear `embedding`, `embedding_model`, and `embedding_updated_at` in the same transaction (§3.1). A background task regenerates the vector; public requests never repair it. Regeneration is not left to manual invocation — see §6.2.

The HNSW index remains cosine-based and is recreated as a partial index over non-null embeddings (`WHERE embedding IS NOT NULL`) if the existing index definition is not partial. **This rebuild is not additive and not safe to run inside the migration transaction**: it is built with `CREATE INDEX CONCURRENTLY` in an Alembic `autocommit_block()` (or as an explicit operational step the migration prints), the old index is dropped only after the new one reports `indisvalid = true`, and the runbook records the expected build duration for the production row count.

Dense queries require `hnsw.ef_search` to be at least as large as the largest dense candidate pool they request (§4.2, §5.1). Each dense query sets `SET LOCAL hnsw.ef_search = <pool_size>` (clamped to a sane maximum) inside its transaction; the default of 40 is too small for the pool sizes in this design and would silently truncate results.

### 3.3 Active embedding model

Production exposes one explicit `ACTIVE_EMBEDDING_MODEL` identifier and one provider configuration. All job and query vectors compared in a request come from that model.

`ACTIVE_EMBEDDING_MODEL` must name the model the configured provider actually runs — it is not a free-form label. The repository currently ships three overlapping settings (`EMBEDDING_MODEL`, `CF_EMBEDDING_MODEL`, and the `sentence-transformers` code default) that name different models, and `sentence-transformers` is not an installed dependency, so the real production embedder is Cloudflare Workers AI (`@cf/baai/bge-small-en-v1.5`). Phase 2 resolves this:

- `ACTIVE_EMBEDDING_MODEL` is derived from / validated against the selected provider. If the provider is Cloudflare Workers AI, `ACTIVE_EMBEDDING_MODEL` equals `CF_EMBEDDING_MODEL`; if a local sentence-transformers model is the provider, that package becomes a real dependency and the identifier is its fully-qualified name.
- Production startup rejects a configuration where `ACTIVE_EMBEDDING_MODEL` does not match the reachable provider, or where no non-fallback provider is configured.
- The stored `embedding_model` on each row is the identifier of the provider that actually produced that vector, written in the same transaction as the vector.

The embedding entry point must surface the provider outcome rather than silently degrading. `get_embedding()` / the query embedder returns a result that distinguishes "provider produced this vector" from "fell back to the deterministic hash". The deterministic hash embedding remains available only when `ENVIRONMENT` is `development` or `test`; in production a fallback is raised as `EmbeddingUnavailableError`, never returned.

## 4. Indexed hybrid retrieval

### 4.1 Request validation

`HybridSearchRequest.query` is trimmed and must contain at least one non-whitespace character. `top_k` remains between 1 and 100. Dense and sparse weights must be non-negative and their sum must be greater than zero; the service normalizes them to sum to one.

All metadata filters use bound SQL parameters. Sort fields and SQL fragments are selected from internal allow-lists, never interpolated from request strings.

### 4.2 Dense branch

The query text is embedded exactly once. PostgreSQL returns dense candidates ordered by cosine distance:

```sql
ORDER BY jobs.embedding <=> CAST(:query_embedding AS vector)
```

Dense similarity is `1 - cosine_distance`, clamped to `[0, 1]`. Only rows with the active embedding model participate.

The dense candidate-pool size is:

```text
min(500, max(100, top_k * 5))
```

The dense query sets `SET LOCAL hnsw.ef_search` to at least that pool size within its transaction (§3.2). Metadata filters are applied before ordering so the HNSW scan searches the relevant market. The query returns only IDs, distance/similarity, and rank until the fused IDs are known.

### 4.3 Lexical branch

PostgreSQL parses the query with `websearch_to_tsquery('english', :query)` and retrieves candidates where:

```sql
jobs.search_document @@ parsed_query
```

Candidates are ordered by `ts_rank_cd(search_document, parsed_query)` descending, then job ID ascending. The lexical pool uses the same bounded formula as the dense pool.

If language-specific stemming becomes necessary later, it requires a separate taxonomy/language design. This specification uses the English configuration consistently for indexing and querying.

### 4.4 Reciprocal Rank Fusion

RRF operates on the union of IDs returned by the two bounded branches:

```text
score(job) = dense_weight / (60 + dense_rank), when dense_rank exists
           + sparse_weight / (60 + sparse_rank), when sparse_rank exists
```

A job absent from a branch receives no contribution from that branch. Zero-score and non-matching rows are not assigned synthetic terminal ranks.

Final order is:

1. RRF score descending;
2. dense similarity descending;
3. lexical score descending;
4. job ID ascending.

Only after selecting the first `top_k` IDs does the service load complete `JobResponse` records and relationships.

### 4.5 Failure behavior

- If query embedding generation fails in production — including the case where the provider is unreachable and only the deterministic hash fallback could be produced — the embedder raises `EmbeddingUnavailableError` and the hybrid endpoint returns HTTP `503`; it does not claim hybrid or semantic retrieval occurred and does not fall back to a hash vector.
- If the lexical query contains no searchable lexemes, the dense branch may still return results.
- Jobs missing active embeddings may appear through the lexical branch, with `dense_rank` and `dense_score` absent.
- Database errors return the existing structured API error shape and a request ID.

The response adds `retrieval_mode`, whose value is `hybrid`, `dense`, or `lexical`, and makes branch ranks/scores optional when that branch did not contribute. Under normal production configuration a nonempty query is `hybrid`; the other values support explicit operational degradation and test environments without inventing scores.

## 5. Candidate matching

### 5.1 Candidate retrieval stage

The matcher first extracts canonical skills and produces one candidate embedding with the active model. It then requests two bounded pools under the selected region and seniority filters:

- up to 200 dense candidates by pgvector cosine distance, with `hnsw.ef_search` set to at least 200 for that query so the "best match after row 200 ranks first" guarantee holds;
- up to 200 lexical candidates from a query containing the extracted canonical hard-skill names, extracted tech-stack names not already present as hard skills, and the request's seniority value when supplied.

The lexical candidate query does not include arbitrary résumé prose, names, email addresses, phone numbers, or soft skills. Terms are deduplicated case-insensitively and ordered by canonical label before being joined, making the query stable for identical extracted profiles.

The union is fused by the same RRF semantics and capped at 300 unique jobs before exact fit scoring. The cap is deterministic after the tie-break rules in §4.4.

This stage replaces `select(Job).limit(200)`. It is candidate selection, not the final fit score, and therefore does not change the documented 50/20/30 formula.

### 5.2 Exact scoring stage

For each selected job:

- hard-skill overlap contributes at most 50 points;
- soft-skill overlap contributes at most 20 points;
- cosine similarity contributes at most 30 points;
- a missing or incompatible job embedding contributes 0 semantic points, not 15;
- explanations describe semantic similarity as strong only when the measured percentage meets a defined threshold of at least 70%; otherwise they use neutral wording;
- match reasons identify unavailable semantic evidence when vector points are zero due to missing data.

Final match order is `fit_score DESC, job_id ASC`.

### 5.3 Response counts

`CandidateMatchResponse` distinguishes:

- `total_eligible`: count of jobs matching region and seniority filters;
- `total_evaluated`: number of unique candidates exactly scored, at most 300;
- `total_qualified`: evaluated jobs meeting `min_fit_score` before response truncation;
- `total_matches`: number returned after applying the request `limit`;
- `matches`: the returned ordered list.

The existing `total_evaluated` and `total_matches` fields retain their names but receive these precise semantics. New fields are additive.

No field may describe the evaluated pool as the entire market when `total_eligible > total_evaluated`.

## 6. Backfill and operational tooling

### 6.1 Search-document backfill

The Alembic migration creates the column and function. A separate idempotent command refreshes documents in primary-key batches of 500, commits each batch, records progress, and can resume after interruption.

Completion verification requires:

- every job has a non-null `search_document`;
- representative title, company, skill, and description searches match expected rows;
- the GIN index is valid.

### 6.2 Embedding backfill

An idempotent background command selects rows whose embedding is absent or has the wrong model. It embeds in provider-supported batches of at most 100, stores vector and provenance atomically, retries transient provider failures with bounded exponential backoff, and stops on permanent authentication/configuration errors.

The command logs counts and job IDs but never logs full descriptions or candidate text.

**Continuous regeneration.** Triggers null embeddings on ongoing edits and ingestion, so a one-off backfill is not enough to hold the 95% activation floor (§6.3). The embedding backfill also runs as a scheduled Celery Beat task (default: every 15 minutes) that processes a bounded batch of null/wrong-model rows. The runbook states the tolerated staleness window (a job may be search-visible only lexically for up to one scheduled interval after a search-relevant edit). Ingestion write paths may additionally enqueue a targeted re-embed task for the jobs they touch.

### 6.3 Feature activation

`POSTGRES_INDEXED_RETRIEVAL_ENABLED` is both a **runtime implementation switch** and a startup gate:

- At request time, `hybrid_search_jobs()` and the matcher's candidate selection branch on it. `false` → the pre-Phase-2 in-memory implementation runs unchanged. `true` → the bounded PostgreSQL repository runs.
- At production startup, if the flag is `true`, the worker evaluates the activation status below and refuses to start if it fails.
- `false` is the deployment default until both backfills pass.

Activation requires:

- current Alembic head;
- valid GIN and HNSW indexes (`indisvalid`);
- 100% search-document coverage;
- at least 95% active-model embedding coverage, with the remainder still searchable lexically;
- successful PostgreSQL acceptance tests.

The in-memory full-scan implementation stays in the codebase, reachable via the flag, for exactly one stable release on the indexed path. A named follow-up release then deletes it. There is no permanent dual path.

## 7. Performance requirements

On a seeded PostgreSQL dataset of at least 10,000 jobs:

- neither search nor matching loads all eligible ORM rows;
- each retrieval branch returns no more than its configured pool size;
- query plans use the GIN index for selective lexical queries and the HNSW index for dense ordering;
- the search request generates exactly one query embedding and zero job embeddings;
- the matcher generates exactly one candidate embedding and zero job embeddings;
- p95 hybrid retrieval excluding external query-embedding latency is below 300 ms on the reference development database;
- p95 exact scoring of the 300-row candidate pool is below 500 ms.

Performance tests record query plans as artifacts. Timing failures are reported separately from correctness failures to reduce flaky unit tests.

## 8. Test requirements

### 8.1 Algorithm tests

- RRF includes only branches in which a job appears.
- Weight normalization is correct and rejects a zero total.
- Tie-breaking is stable across repeated runs.
- Missing vectors contribute zero semantic points.
- incompatible `embedding_model` rows are excluded from dense retrieval.

### 8.2 PostgreSQL integration tests

- search by title, company, hard skill, tech stack, and description returns the intended row.
- changing a company or hard-skill name refreshes affected search documents.
- metadata filters are applied inside both retrieval queries.
- dense and lexical queries return bounded pools.
- `EXPLAIN (ANALYZE, BUFFERS)` demonstrates index-assisted plans on the reference dataset, and confirms `hnsw.ef_search` is applied at the configured pool size.
- a job inserted as row 201 with the strongest fit ranks first in matching (with `hnsw.ef_search` ≥ 200).
- a search-relevant update to a job nulls its embedding without recursive trigger firing, and the job remains lexically searchable.
- `total_eligible`, `total_evaluated`, `total_qualified`, and `total_matches` remain distinct and accurate.
- embedding-provider failure produces `503` without deterministic production fallback.
- with `POSTGRES_INDEXED_RETRIEVAL_ENABLED=false`, the pre-Phase-2 in-memory path still serves search and matching.

These tests run against the disposable PostgreSQL 16 + pgvector database from a `postgres` pytest marker and a CI service container (program spec §5). They are skipped explicitly, not silently, when only SQLite is available. The plan adds the fixture and marker registration before any retrieval task.

### 8.3 API and frontend contracts

- the hybrid search endpoint currently has no SPA consumer (`frontend/script.js` calls `/api/v1/match`, `/api/v1/jobs`, and `/api/v1/analytics/overview` only). Its contract is verified at the API/OpenAPI level and against `HybridSearchResponse` model validation; no new SPA renderer is in scope.
- the match response *is* consumed by the SPA. `validateCandidateMatchResponse()` is updated to require `total_eligible`, `total_evaluated`, `total_qualified`, and `total_matches` as numbers without inventing fallback values, and existing complete match responses remain renderable.
- optional missing branch scores are not displayed as zero-percent measured similarity unless zero was actually measured.
- malformed or incomplete responses continue to render the truthful unavailable state.
- OpenAPI documents the new count fields, optional branch fields, and `retrieval_mode`.

## 9. Rollout and rollback

1. Apply the schema migration `0012_postgres_indexed_retrieval` (chained from `0011_runtime_schema_authority`). It defines a complete `downgrade()` that drops the triggers, then the function, then the GIN and partial-HNSW indexes, then the three columns. The partial-HNSW rebuild is performed `CONCURRENTLY` outside the migration transaction (§3.2).
2. Run search-document and embedding backfills; enable the scheduled re-embed task (§6.2).
3. Verify coverage, index validity (`indisvalid`), query plans, `hnsw.ef_search`, and shadow result comparisons.
4. Enable indexed retrieval by setting `POSTGRES_INDEXED_RETRIEVAL_ENABLED=true` on one instance, then all instances. The flag selects the served implementation at request time; the pre-Phase-2 in-memory path stays in the codebase and remains reachable while the flag is `false`.
5. Remove the in-memory full-scan implementation only in the follow-up release after one stable release on the indexed path.

Rollback is: set `POSTGRES_INDEXED_RETRIEVAL_ENABLED=false` (takes effect without redeploy) and/or restore the previous application version. Schema columns, functions, and indexes remain until a later controlled `alembic downgrade`; backfilled embeddings and search documents do not alter source job data.
