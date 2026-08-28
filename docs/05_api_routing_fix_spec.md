# SkillPulse AI — Spec: Live Backend on Cloudflare (D1 + Vectorize + Workers AI)

**Status:** Draft — ready to implement, phased
**Owner:** —
**Related:** `docs/03_cloudflare_deployment_guide.md` (superseded by this doc for the backend target), `wrangler.toml.example`, `docs/06_ui_refactor_spec.md`

**Revision note:** the first draft of this spec targeted Render + Neon as the lowest-risk host. The decision has since changed: backend **and** database move to Cloudflare — Python Workers (FastAPI), D1 (relational data), Vectorize (embeddings), Workers AI (embedding generation). That's a materially bigger migration than a hosting swap, so this version is phased: each phase ships something real and reversible, instead of one big-bang cutover.

---

## 1. Problem (unchanged from the original diagnosis)

`skillpulse.pages.dev` is a static Cloudflare Pages deployment with no backend behind it:

- `frontend/script.js:4` / `frontend/admin.js:4` — `const API_BASE = window.API_BASE_URL || '';`, never set on the deployed page, so every fetch is same-origin.
- `frontend/_redirects`' SPA catch-all (`/* → /index.html 200`) swallows same-origin `/api/v1/*` requests, returning HTML with a `200`.
- The frontend's failure paths render hardcoded fixture data (`renderFallbackMatch`, seeded job arrays) instead of an explicit error state, so the live site silently shows fake jobs at fake companies no matter what.
- No backend is deployed anywhere. `wrangler.toml.example` names a `skillpulse-api` Worker that was never instantiated.

## 2. Target architecture

```
Cloudflare Workers (Python, FastAPI via ASGI adapter)
  ├─ Workers Static Assets  → serves frontend/ (kills the _redirects ambiguity: one router, not two)
  ├─ D1 binding             → relational data (jobs, companies, skills, search_terms, error_logs, ...)
  ├─ Vectorize binding      → 384-d job/résumé embeddings + similarity search
  └─ Workers AI binding     → @cf/baai/bge-small-en-v1.5 embedding generation
```

This is a genuine architecture change, not a redeploy. Two things make it more tractable than it sounds once you actually read the current code:

1. **`services/embedding_service.py` already has a Workers AI call path.** `_call_cloudflare_workers_ai()` (line 28) already hits `@cf/baai/bge-small-en-v1.5` via `CF_ACCOUNT_ID`/`CF_API_TOKEN` as *tier 1* of a fallback cascade (Workers AI → local `sentence-transformers` → deterministic hash fallback). Moving to Workers AI as primary is a matter of making tier 1 non-optional and dropping the other two tiers in production, not building new integration.
2. **`services/hybrid_search_service.py` does not use `pgvector` SQL at all today.** `hybrid_search_jobs()` (line 94) loads every filtered job into a Python list and computes cosine similarity **in-memory, in a loop** (lines 168–179) — there is no ANN index, no vector column query, nothing pgvector-specific to migrate away from. Replacing that loop with a Vectorize `query()` call is a genuine upgrade (real ANN search instead of O(n) brute force), not a lateral rewrite.

The real risk is the relational layer: this app leans hard on **SQLAlchemy ORM** (`entities/*.py`, `database.py`, 12 Alembic migrations, every `services/*_hm.py` and `api/v1/*.py` route). There is no confirmed SQLAlchemy dialect for D1 — D1 is accessed from a Worker via a **binding + FFI call pattern** (`env.DB.prepare(query).bind(...).run()`), not a DBAPI connection string. That gap is the single biggest unknown in this spec and is treated as its own phase-gated spike below, not assumed solved.

---

## 3. Phases

### Phase 0 — Stop lying to the user (do this regardless of host, ship immediately)

Independent of where the backend ends up, fix the failure-mode bug in the current frontend:

- `frontend/script.js`: replace the automatic `renderFallbackMatch(...)` / seeded-jobs-on-fetch-failure behavior with an explicit state: *"Live data unavailable right now"* + the existing opt-in sample-persona cards (keep those — they're clearly labeled and user-initiated; the bug is *silent, automatic* substitution, not demo content existing at all).
- Add `frontend/config.js` (`window.API_BASE_URL = "..."`, version-controlled, not a secret) loaded before `script.js`/`admin.js`, so the target backend is a one-line, reviewable change no matter which phase below it points at.

This phase alone fixes the "shows fake jobs" symptom even before Phase 1 ships. Ship it first.

### Phase 1 — FastAPI on a Python Worker, data layer unchanged (bridge state)

Goal: get a real Cloudflare-hosted backend live, serving real data, **without** touching the persistence layer yet. This isolates "can FastAPI run on Workers and serve this app" from "can this app's ORM run on D1" — two different risks, don't take them on at once.

1. Follow Cloudflare's current FastAPI-on-Python-Workers guide (`developers.cloudflare.com/workers/languages/python/packages/fastapi/`, confirmed current as of this spec): `src/main.py` exporting the existing `app` object from `app.py` through the built-in ASGI adapter (`asgi.fetch(app, request, self.env)`), `pyproject.toml` declaring `fastapi` and this project's other pure-Python dependencies, `wrangler.jsonc` with `compatibility_flags: ["python_workers"]`.
   - **Spike first, before committing:** verify which of this project's actual dependencies (`sqlalchemy`, `pydantic`, `passlib`/whatever auth hashing is in use, `requests`) load under Pyodide. `sentence-transformers` (pulls in `torch`) will not — that's expected and fine, since Workers AI replaces it. Anything else that fails needs a pure-Python substitute before Phase 1 is done, not discovered after.

   **Dependency-spike result (2026-08-21; not the Hyperdrive result):** Cloudflare's minimal FastAPI example ran under local `pywrangler`/Pyodide and returned `HTTP 200` (`{"runtime":"python-worker","fastapi":"loaded"}`); its first request took 28.8 seconds and a warm request took 176 ms. The project's current Postgres drivers cannot be packaged: `psycopg2-binary>=2.9.9` and `asyncpg>=0.29.0` each fail Pyodide resolution with “no usable wheels.” SQLAlchemy itself resolves into the Worker bundle, but the FastAPI + SQLAlchemy probe did not complete a request within two bounded 30-second windows. Cloudflare's current Python package documentation also states that synchronous HTTP clients are unsupported, so the app's `requests` call path must not run in Worker mode. Probe sources are under `spikes/python_worker_dependencies/` and `spikes/python_worker_fastapi_baseline/`.

   **Hyperdrive provisioning preflight (2026-08-21; Python Worker spike still pending):** Cloudflare's current pricing documentation confirms that Hyperdrive is included in both Workers Free and Workers Paid. The Free allocation is 100,000 database queries per day and up to 10 configured databases, with over-limit operations failing rather than becoming paid overages. A temporary, cache-disabled configuration named `skillpulse-python-spike-20260821` (ID `8a0dc524afec430f95df4f46178617ea`) was created against the test Supabase PostgreSQL origin. Cloudflare accepted and encrypted the direct database credential; `wrangler hyperdrive list/get` verified PostgreSQL on port 5432, database/user `postgres`, caching disabled, and an origin connection limit of 20. This proves the origin configuration is valid, but it is **not** the required Hyperdrive-from-Python result: the standalone Python Worker must still open the binding and run `SELECT 1` before any real route is wired to it.
2. Serve `frontend/` via Workers Static Assets (`assets.directory = "./frontend/"`, `run_worker_first: true`), with FastAPI's catch-all route proxying unmatched paths to the `ASSETS` binding. This structurally removes the `_redirects` ambiguity from `docs/05`'s original diagnosis — there's one router (FastAPI) deciding what's an API route vs. a static file, not a Pages redirect table guessing.
3. Database for this phase: **keep Neon Postgres, connect through Hyperdrive.** This is the one part of this spec carrying real uncertainty — every documented Hyperdrive example uses a JS driver (`postgres.js`, `mysql2`); a Python driver (`psycopg`/`asyncpg`) talking through Hyperdrive from inside a Pyodide Python Worker is not something Cloudflare's docs currently show working. **Spike this explicitly**: a Worker that does nothing but open a Hyperdrive-backed connection and run `SELECT 1` via SQLAlchemy, before porting any real route to it. If it doesn't work, the fallback for this phase only is: keep the FastAPI-on-Workers migration, but reach Postgres via Hyperdrive's raw TCP socket API directly (bypassing SQLAlchemy for this phase) or defer Phase 1's Postgres connectivity and go straight to Phase 2's D1 migration for the parts that block on it.

   **Hyperdrive-from-Python spike result (2026-08-21): DIDN'T WORK — Phase 1 stops here.** The isolated source is under `spikes/hyperdrive_python/`. `psycopg2-binary` and `asyncpg` could not be packaged for Pyodide in the preceding dependency spike, so the real Worker used SQLAlchemy 2 plus the pure-Python `pg8000` driver. Pywrangler resolved and bundled both packages, and the deploy dry run showed only the intended `HYPERDRIVE` binding. Worker `skillpulse-python-hyperdrive-spike-20260821` deployed successfully (version `a3c9a017-30e3-4a92-8cef-775fc7bb015c`) against the cache-disabled Hyperdrive configuration. Two consecutive live requests reached the SQLAlchemy `SELECT 1` stage and returned `HTTP 500` with `{"ok":false,"runtime":"python-worker","database_path":"sqlalchemy+pg8000+hyperdrive","stage":"select_1","error_type":"OSError"}`. This demonstrates that dependency packaging and binding injection work, but the synchronous pure-Python driver cannot open the required database socket in the Python Worker runtime. Per the migration checkpoint, no production route was wired to Hyperdrive and no raw-TCP/JavaScript-FFI workaround was attempted.
4. CORS + cookie changes carried over from the original diagnosis, still required: set `CORS_ORIGINS` to the real frontend origin, and change `samesite="lax"` → `samesite="none", secure=True` on the admin session cookie (`api/v1/auth.py:81`, `app.py:215`) — required the moment frontend and backend aren't guaranteed same-origin, independent of which Cloudflare product hosts them.

**Phase 1 exit criteria:** the live site serves real data from the real dataset, end to end, still backed by Postgres. Nothing about the UI or the data model changed — only the host.

### Phase 1a — Resolve the Hyperdrive-from-Python blocker

**Root cause (2026-08-21).** `pg8000` — the only pure-Python PostgreSQL driver that could be packaged for Pyodide at all — opens a real blocking POSIX `socket.socket()`. The Python Workers sandbox does not expose one: the *only* outbound network primitives reachable from a Worker are the JS `fetch()` API and the JS `connect()` TCP Sockets API (`developers.cloudflare.com/workers/runtime-apis/tcp-sockets/`), both of which live behind the FFI, not behind `socket.socket()`. Every documented Hyperdrive driver (`postgres.js`, `mysql2`) is JS-only for exactly this reason — those libraries were rewritten against `connect()` instead of Node's raw `net` module. No Python driver in this ecosystem has had that rewrite done to it. The `OSError` at the `select_1` stage in the 2026-08-21 spike is consistent with `pg8000`'s socket layer failing to open at all, not a query-level or auth-level failure — so there is no configuration fix here, only an architecture change.

**Two credible unblocks exist**, both confirmed against Cloudflare's current documentation (checked 2026-08-21, after the spike failure):

- **(A) Skip the Postgres bridge, run Phase 3's gating spike now — recommended.** Cloudflare publishes a first-party, working pattern for exactly the thing Phase 3 requires as its gate: a Python Worker reading a real D1 table via `self.env.DB.prepare(query).bind(...).run()` (`developers.cloudflare.com/d1/examples/query-d1-from-python-workers/`, `developers.cloudflare.com/d1/worker-api/prepared-statements/`). This isn't a Python driver problem at all — D1 access from a Python Worker goes through the same FFI binding mechanism already proven to work in the 2026-08-21 dependency spike (bindings resolved and injected cleanly; only the Postgres *driver* failed), not through a socket. Running this spike now, against this project's real schema (starting with the simple `companies` table — `entities/company.py`, `id` + `name`, no relationships), does two things at once: it unblocks a live backend today, and it retires Phase 3's biggest unknown early instead of leaving it for later. If it passes, Phase 1 and Phase 3 collapse into one migration — go straight to D1 for the routes this was blocking, rather than standing up Postgres connectivity on Workers at all.
- **(B) RPC bridge to a companion JS Worker — fallback, keeps Postgres for now.** Python and JavaScript Workers can now call each other directly via Workers RPC through a Service Binding, with the Pyodide FFI handling type conversion automatically (GA'd 2026-08-03: `developers.cloudflare.com/changelog/post/2026-08-03-python-javascript-rpc/`). A small companion Worker, written in TS, would own the `HYPERDRIVE` binding and run queries with `postgres.js` — the combination Cloudflare's own Hyperdrive docs demonstrate working. The FastAPI Worker calls it as `await self.env.DB_BRIDGE.query(sql, params)`. This preserves Phase 1's original promise (only the host changes, the data model doesn't) but means building — and later deleting — bridge infrastructure whose only job is to disappear once Phase 3 lands anyway. SQLAlchemy Core's expression language can still be used query-by-query on the Python side (`.compile(dialect=postgresql.dialect())` renders SQL + params without a live DBAPI connection), but ORM session features (lazy-loaded relationships, identity map) don't survive the RPC boundary and would need to be reassembled manually — the same shape of rewrite Phase 3 already anticipated, just arriving one phase early.

**Decision: go with (A).** It is the only one of the two backed by a Cloudflare-published, driver-free, already-working example rather than a documented-for-JS-only pattern being adapted for the first time. It spends the ORM-rewrite effort once, on the real target (D1), instead of once now (bridge Worker) and again later (D1 migration proper). (B) stays documented here as the fallback if the D1 read spike below fails for a reason specific to this project's schema.

**Immediate next action:** the smallest possible proof — a standalone Python Worker, bound to a real D1 database seeded with the `companies` table, returning its rows as JSON. Spike scaffold and results tracked at `spikes/d1_python_read/` once run; implementation prompt: [`docs/prompts/phase1a_d1_read_spike_prompt.md`](prompts/phase1a_d1_read_spike_prompt.md).

**D1-from-Python gating-spike result (2026-08-21): WORKED — Phase 1a and Phase 3 are unblocked.** The isolated source is under `spikes/d1_python_read/`. Remote D1 database `skillpulse-d1-read-spike` (ID `72bb6846-b92a-47ca-9c69-b62539b2b232`, WEUR) was seeded with the project-shaped `companies` table and verified remotely with IDs 1–3 for `Ambev`, `Eurofarma`, and `Nubank`. Worker `skillpulse-python-d1-read-spike-20260821` deployed successfully (version `d18e1239-ab33-4e41-85ab-1087525c4c0a`) with the `DB` binding after Pywrangler attached its 28 required vendored Python SDK modules. The handler ran `self.env.DB.prepare("SELECT id, name FROM companies ORDER BY id").run()` through the documented D1 FFI binding path; this static query has no value parameter to bind. Two consecutive post-deployment requests returned `HTTP 200` with the identical body `{"ok": true, "runtime": "python-worker", "database_path": "d1-ffi-binding", "results": [{"id": 1, "name": "Ambev"}, {"id": 2, "name": "Eurofarma"}, {"id": 3, "name": "Nubank"}]}`. The first two probes made immediately after publication returned Cloudflare's pre-handler `HTTP 404` / `error code: 1042`; a subsequent log-correlated request and both required repeat captures returned the stable `HTTP 200` response above, with no Worker error stage reached. Direct `npx wrangler deploy` also failed before creating a version because it bypassed Python dependency vendoring (`ModuleNotFoundError: No module named 'workers'`); the current Python Workers example's `uv run pywrangler deploy` path generated `pylock.toml`, attached the SDK modules, and produced the deployed version cited here.

**Migration consequence.** Phase 1 and Phase 3 now collapse into one D1 migration, as anticipated by the Phase 1a decision: the project will migrate blocked relational routes directly to D1 instead of establishing an interim Postgres connection from Python Workers. Phase 1's remaining Postgres/Hyperdrive-specific work in §3, Phase 1 item 3 is superseded; no raw-TCP workaround or RPC bridge will be pursued on the selected path. Phase 3's gate is satisfied by this same spike, not by a duplicate run.

### Phase 2 — Vectors move to Vectorize + Workers AI

This phase is lower-risk than Phase 3 and delivers a real improvement (ANN search replacing the in-memory loop), so do it before touching the relational layer.

1. Create a Vectorize index: 384 dimensions, cosine metric (`npx wrangler vectorize create skillpulse-jobs --dimensions=384 --metric=cosine`). Confirm at creation time whether Vectorize requires the Workers Paid plan on this account — Cloudflare's own docs are inconsistent on this point (a limits page states a Free-plan allocation exists; a pricing page states Vectorize is Paid-plan-only). Resolve this before planning around a specific cost, don't assume either answer.
2. `services/embedding_service.py`: make `_call_cloudflare_workers_ai()` (already implemented, line 28) the only path in the Worker deployment — drop the `sentence-transformers` and deterministic-fallback tiers from `get_embedding`/`get_embeddings_batch` for that environment (keep them for local dev/tests, where Workers AI isn't reachable). `_JOB_EMBEDDING_CACHE` (line 272, already flagged elsewhere as unbounded) goes away entirely — Vectorize *is* the cache.
3. `services/hybrid_search_service.py`: replace the manual `dense_scored` loop (lines 168–179) with a single `env.VECTORIZE.query(query_embedding, topK=top_k, filter={...})` call, using Vectorize's metadata filter for the region/workplace/seniority facets currently applied as an in-memory Python filter (lines 126–159). Keep the sparse/lexical scoring (lines 60–91) and RRF fusion (lines 41–57, 198–230) as-is — those aren't vector-store-specific and don't need to change.
4. Backfill: batch-embed all 1,490 (or however many are live at cutover) jobs into the new Vectorize index via Workers AI, off the request path — a one-time script, not something that runs per-request.

**Phase 2 exit criteria:** search results are identical in shape to before, but ranked by a real ANN index instead of a per-request Python loop, and no job embedding is generated more than once.

### Phase 3 — Relational data moves to D1 (highest risk, do last, gate on a spike)

**Do not start this phase until someone has actually built the smallest possible proof: a Python Worker reading one table from a real D1 database and returning it as JSON, using whatever access pattern (native binding via FFI, or D1's HTTP API called from Pyodide) turns out to work.** Nothing below should be scheduled against a calendar until that spike exists — this is the one part of the whole migration where "should work based on the docs" and "actually works inside a Pyodide sandbox" might diverge.

This gating spike is now the same spike Phase 1a runs to unblock itself (`spikes/d1_python_read/` — see Phase 1a above) — don't duplicate it here, just confirm its result before proceeding.

Once the spike is confirmed:

1. Schema: port the 12 Alembic migrations (`alembic/versions/`) to D1-compatible SQLite DDL — D1 *is* SQLite, so this is much closer to the project's existing local SQLite dev setup (`database.py`) than to the Postgres schema. The Postgres-specific pieces to watch: any `ARRAY`/`JSONB` column types, and the `pgvector` embedding column on `Job` — that column is dropped entirely in this architecture (embeddings live in Vectorize, correlated by job ID, not in a relational column).
2. Data access: every `services/*.py` and `api/v1/*.py` function currently issuing `db.query(...)`/`select()` through a SQLAlchemy `Session` needs a decision, per the spike's outcome:
   - If a workable SQLAlchemy-over-D1 path exists (custom dialect, or D1's HTTP API wrapped in one), the ORM layer and relationships (`job.hard_skills`, `job.company`, `job.city`, etc., used throughout `hybrid_search_service.py` and elsewhere) can largely survive unchanged.
   - If not, the fallback is rewriting data access to raw `env.DB.prepare(sql).bind(...).run()` calls and reassembling relationships manually in Python — a genuinely large, mechanical rewrite touching most of `services/`, `api/v1/`, and `entities/`. Scope that as its own tracked project if it comes to this, not a subtask of this spec.
3. Migrate data: export the live Postgres dataset (or SQLite `jobs.db` if Phase 1 never got Postgres working) and import into D1 (`wrangler d1 execute --file`).
4. Cut the frontend/Worker over to D1, verify against the same acceptance checklist used for Postgres, then decommission Neon + Hyperdrive.

---

## 4. Acceptance criteria (cumulative — each phase's criteria must hold before starting the next)

**Phase 0**
- [x] Killing the API and reloading `/jobs` shows an explicit "live data unavailable" state, never silently-swapped fixture jobs. Verified 2026-08-21 with a local SPA server returning `503` for `/api/*`; Browser showed the explicit unavailable state and no fixture rows. `node --test tests/frontend_api_routing.test.js`: 3/3 passed.
- [x] `frontend/config.js` exists, is version-controlled, and both `index.html`/`admin.html` load it before their app script. Verified 2026-08-21 by `tests/test_api_routing_fix.py`: 4/4 passed.

**Phase 1**
- [ ] `curl https://<worker-url>/health` returns real DB-connectivity status.
- [ ] `curl https://<worker-url>/api/v1/jobs?page=1&page_size=5` returns real rows (`Ambev`, `Eurofarma`, etc.).
- [ ] The deployed frontend, served from the same Worker via Static Assets, shows ~1,490 roles, not 4.
- [ ] Admin login's session cookie is present on the *next* request's `Cookie:` header (proves the `SameSite=None` fix worked, not just that login returned 200).
- [x] The Hyperdrive-from-Python spike result (worked / didn't) is written down in this doc before Phase 1 is marked done, whichever way it went. Recorded 2026-08-21 as **didn't work** with the deployed Worker version and repeatable `HTTP 500`/`OSError` evidence above.

**Phase 1a**
- [x] The root cause of the Hyperdrive-from-Python failure (blocking-socket driver vs. sandboxed runtime) is written down with a source, not just the symptom — done above.
- [x] Resolution path (A or B) is chosen and recorded here with a reason, not left as two open options — done above: **(A)**.
- [x] The `companies`-table D1 read spike (`spikes/d1_python_read/`) returns real rows as JSON from a real D1 database via `self.env.DB.prepare(...).run()` (no bind parameters were needed for the static query), with the deployed Worker version and response body recorded above.
- [x] This result also satisfies Phase 3's gating spike requirement below — cross-referenced there instead of re-running it.

**Phase 2**
- [ ] A search for the same query before/after returns a materially similar ranked list (sanity check that the migration didn't silently break relevance), sourced from Vectorize, not the old in-memory loop — confirm by removing `_JOB_EMBEDDING_CACHE`/the local loop code and re-running the test suite (`tests/test_hybrid_search_and_matcher.py`).
- [ ] Re-requesting the same job's embedding does not re-call Workers AI (proof Vectorize is acting as the store, not a cache miss every time).

**Phase 3**
- [x] The read-one-table-from-D1 spike is confirmed working via the native Python D1 FFI binding; see the Phase 1a result above for the deployed version and repeatable response evidence.
- [ ] Full test suite (`pytest`) passes against D1 in place of Postgres/SQLite.
- [ ] Neon + Hyperdrive are decommissioned only after D1 has run in production for a defined soak period — not on cutover day.
