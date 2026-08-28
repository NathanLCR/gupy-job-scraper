# Cloudflare Routing and UI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `docs/05_api_routing_fix_spec.md` and `docs/06_ui_refactor_spec.md` in their required order, with Cloudflare feasibility spikes and acceptance evidence at every gate.

**Architecture:** A Python Worker exports the existing FastAPI app through Cloudflare's ASGI adapter and serves `frontend/` through a Static Assets binding. Hyperdrive/Postgres remains the Phase 1 bridge only if a real Python Worker `SELECT 1` spike succeeds; Workers AI plus Vectorize replace local dense embedding generation in Phase 2; D1 work begins only after a real bound Python Worker reads a table successfully. The frontend remains vanilla HTML/CSS/JS and uses shared design tokens.

**Tech Stack:** Python 3.13 on Cloudflare Python Workers/Pyodide, FastAPI, Cloudflare Static Assets, Hyperdrive, PostgreSQL/SQLAlchemy, Workers AI, Vectorize, D1, vanilla HTML/CSS/JavaScript, pytest, Node test runner, Browser visual verification.

**Specs:** `docs/05_api_routing_fix_spec.md`, `docs/06_ui_refactor_spec.md`

## Global Constraints

- Preserve the order Phase 0 -> Phase 1 Hyperdrive spike -> Phase 1 integration -> Phase 2 dashboard plan check -> Phase 2 -> Phase 3 D1 spike -> Phase 3 -> UI refactor.
- Stop immediately if the Hyperdrive-from-Python spike fails; do not implement the spec's suggested raw-TCP workaround without new user direction.
- Do not create a Worker, Hyperdrive configuration, D1 database, or Vectorize index that costs money or needs account-level setup without explicit user approval.
- Use the current Cloudflare Python Workers tooling and documentation; Python Workers are beta and use `pywrangler` for local development as of 2026-08-21.
- Keep frontend implementation in vanilla HTML/CSS/JS with no framework or build step.
- Preserve existing uncommitted user changes and do not commit implicitly.
- Use test-first red/green cycles for behavior changes and fresh evidence before every completion claim.
- Use the Browser tool to inspect Jobs, Match, and Market before calling either spec complete.

---

### Task 1: Phase 0 truthful API failure states

**Files:**
- Modify: `frontend/script.js`
- Create or modify: `frontend/config.js`
- Modify: `frontend/index.html`
- Modify: `frontend/admin.html`
- Test: `tests/frontend_api_routing.test.js`
- Test: `tests/test_api_routing_fix.py`

**Interfaces:**
- Consumes: `window.API_BASE_URL: string`, API responses with JSON content types.
- Produces: explicit unavailable UI states and `fetchApiJson(url, options)` that rejects HTML/redirect fallbacks.

- [ ] Run `node --test tests/frontend_api_routing.test.js` and `.venv/bin/python -m pytest tests/test_api_routing_fix.py -q` to establish current behavior.
- [ ] If any required behavior is missing, add one failing observable test for that behavior and verify the expected failure.
- [ ] Make the smallest frontend/config change needed to pass; keep sample personas opt-in only.
- [ ] Re-run both focused suites.
- [ ] Serve the frontend with no API available, open `/jobs` in Browser, and capture evidence that the unavailable state renders without fixture vacancies.
- [ ] Record Phase 0 acceptance results in the task report before starting Phase 1.

### Task 2: Phase 1 Python Worker dependency and FastAPI/Static Assets scaffold

**Files:**
- Create: `src/main.py`
- Create: `pyproject.toml`
- Create: `wrangler.jsonc`
- Create: `frontend/.assetsignore`
- Modify: `app.py` only where Worker-safe routing/lifespan behavior requires it.
- Test: `tests/test_worker_entrypoint.py`

**Interfaces:**
- Consumes: `app.app: FastAPI`, `asgi.fetch(app, request, self.env)`, `self.env.ASSETS.fetch(request)`.
- Produces: `src.main.Default.fetch(request)` as the single Worker entrypoint and same-origin static/API routing.

- [ ] Build a minimal dependency-import spike using the project's actual imported package graph and `uv run pywrangler dev`; record each incompatible package before changing production imports.
- [ ] Write a failing Worker-entrypoint test that proves API paths go through ASGI and unmatched public paths go to Static Assets.
- [ ] Add the minimal Worker entrypoint and current JSONC configuration (`compatibility_date: 2026-08-21`, `python_workers`, `assets.directory: ./frontend`, binding `ASSETS`, `run_worker_first: true`).
- [ ] Configure `.assetsignore` so Pages-only `_redirects`/`_headers` are not uploaded as Worker assets.
- [ ] Run the Worker-entrypoint test, Python suite, and a local `pywrangler` smoke test for `/health`, `/api/v1/jobs`, and `/jobs`.

### Task 3: Phase 1 Hyperdrive-from-Python spike and checkpoint

**Files:**
- Create: `spikes/hyperdrive_python/src/main.py`
- Create: `spikes/hyperdrive_python/pyproject.toml`
- Create: `spikes/hyperdrive_python/wrangler.jsonc.example`
- Modify: `docs/05_api_routing_fix_spec.md`

**Interfaces:**
- Consumes: a real existing Hyperdrive binding and its connection information.
- Produces: an HTTP JSON response containing the SQLAlchemy `SELECT 1` result, or a documented failure with exact runtime evidence.

- [ ] Confirm whether an existing Cloudflare account, Hyperdrive configuration, and reachable Postgres database are available; ask before creating any missing account-level resource.
- [ ] Keep the spike isolated from all production routes and execute it in a real Python Worker runtime.
- [ ] Run `SELECT 1` through SQLAlchemy using the Hyperdrive-backed path and capture deploy/log/curl output.
- [ ] Write `worked` or `didn't work`, date, exact access pattern, and evidence into Phase 1 of `docs/05_api_routing_fix_spec.md`.
- [ ] If the spike fails, stop the task and report the blocker without implementing raw TCP or another workaround.

### Task 4: Phase 1 live Postgres bridge acceptance

**Files:**
- Modify only the Worker entrypoint/config/database integration files proven necessary by Task 3.
- Test: existing API and routing suites plus a focused cookie round-trip integration test.

**Interfaces:**
- Consumes: proven Hyperdrive SQLAlchemy connection path and existing FastAPI routes.
- Produces: same-origin Worker deployment with real PostgreSQL rows and secure admin cookie behavior.

- [ ] Write/verify a failing health test that checks real connectivity rather than a constant `"connected"` value.
- [ ] Wire the proven connection path into the application without changing route response shapes.
- [ ] Verify `SameSite=None; Secure` and that a subsequent request sends the cookie.
- [ ] Capture curl evidence for `/health` and `/api/v1/jobs?page=1&page_size=5`, plus Browser evidence for the live role count.
- [ ] Report every Phase 1 acceptance criterion individually.

### Task 5: Phase 2 account-plan checkpoint and Vectorize/Workers AI design

**Files:**
- Modify: `docs/05_api_routing_fix_spec.md` with dated dashboard observation.
- No resource creation until approval.

**Interfaces:**
- Consumes: signed-in Cloudflare dashboard plan/capability state.
- Produces: an evidence-backed Free/Paid determination for this account and explicit approval request if index creation or Workers AI usage can incur cost.

- [ ] Open the Cloudflare dashboard with Browser and inspect the account's Workers plan and Vectorize creation surface.
- [ ] Compare dashboard state with current official pricing documentation.
- [ ] Record the observed plan requirement/allocation in `docs/05_api_routing_fix_spec.md`.
- [ ] Ask for approval before creating the 384-d cosine index or enabling any billable usage.

### Task 6: Phase 2 Workers AI and Vectorize migration

**Files:**
- Modify: `services/embedding_service.py`
- Modify: `services/hybrid_search_service.py`
- Create: `scripts/backfill_vectorize.py`
- Modify: `src/main.py` and `wrangler.jsonc` for binding injection.
- Test: `tests/test_cloudflare_and_caching.py`
- Test: `tests/test_hybrid_search_and_matcher.py`

**Interfaces:**
- Consumes: Worker bindings `self.env.AI` and `self.env.VECTORIZE`, query text, facet metadata, and job IDs.
- Produces: 384-d Workers AI embeddings, Vectorize ANN hits, unchanged hybrid-search result shape, and an idempotent off-request backfill.

- [ ] Add failing tests for Worker-only binding inference, no local fallback in Worker mode, metadata-filtered Vectorize query, preserved RRF fusion, and reuse of stored job vectors.
- [ ] Implement the minimal binding adapter and remove `_JOB_EMBEDDING_CACHE` plus the in-memory dense loop from Worker execution.
- [ ] Add the idempotent batch backfill using real job IDs and metadata.
- [ ] Verify the focused suites and compare before/after rankings for the same query.
- [ ] Capture evidence that repeated search does not re-embed stored jobs and report every Phase 2 criterion.

### Task 7: Phase 3 standalone real-D1 Python Worker spike

**Files:**
- Create: `spikes/d1_python/src/main.py`
- Create: `spikes/d1_python/pyproject.toml`
- Create: `spikes/d1_python/wrangler.jsonc.example`
- Modify: `docs/05_api_routing_fix_spec.md`

**Interfaces:**
- Consumes: a real bound D1 database containing one known table/row.
- Produces: JSON returned by `await self.env.DB.prepare(...).run()` and a documented access-pattern decision.

- [ ] Ask before creating a D1 database or Worker if no reusable real resource exists.
- [ ] Create/read one known table only in the standalone spike, never through production routes.
- [ ] Capture curl/log output from the deployed Python Worker.
- [ ] Record worked/failed, date, binding API, and response evidence in `docs/05_api_routing_fix_spec.md`.
- [ ] If the spike fails, stop before any schema or repository data-access rewrite.

### Task 8: Phase 3 D1 migration, only after Task 7 succeeds

**Files:**
- Create: D1-compatible schema/migration SQL derived from `alembic/versions/` and `migrations/versions/`.
- Modify: data access files selected by the spike outcome.
- Test: full `tests/` suite against D1.

**Interfaces:**
- Consumes: proven D1 Python binding access, current relational schema, and exported real dataset.
- Produces: unchanged API contracts backed by D1; embeddings remain exclusively in Vectorize.

- [ ] Inventory every PostgreSQL-specific type/operation and write failing contract tests for affected repository functions.
- [ ] Port schema and data access using only the access pattern proven by Task 7.
- [ ] Import real data and run the full suite against D1.
- [ ] Verify all API, auth-cookie, Jobs, Match, and Market acceptance checks.
- [ ] Define and document a production soak period; do not decommission Neon/Hyperdrive during cutover.

### Task 9: UI tokens and anti-AI visual lint

**Files:**
- Create: `frontend/tokens.css`
- Modify: `frontend/style.css`
- Modify: `frontend/admin.css`
- Modify: `frontend/index.html`
- Modify: `frontend/admin.html`

**Interfaces:**
- Produces: shared Option A `signal` tokens, IBM Plex Sans/Mono typography, 4/6/8px radii, flat scrims, and one restrained accent.

- [ ] Announce Option A `signal` with IBM Plex Sans/Mono: teal reinforces data signal and cross-border technical character while keeping dense UI legible.
- [ ] Add a failing static/UI test for duplicated roots, blur, >8px radii, old blue accent, and old font imports.
- [ ] Extract shared tokens and remove prohibited blur/heavy shadow/card nesting patterns.
- [ ] Check every item in `docs/06_ui_refactor_spec.md` section 4 explicitly and record pass/evidence.

### Task 10: Jobs, Match, Market, and Admin UI behavior

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/script.js`
- Modify: `frontend/style.css`
- Modify: `frontend/admin.html`
- Modify: `frontend/admin.js`
- Modify: `frontend/admin.css`
- Modify backend analytics schemas/routes only when real region and coverage fields are absent.
- Test: add focused Node behavior tests and Python API contract tests.

**Interfaces:**
- Consumes: live jobs with region/extraction tier, match items with `hard_points`, `soft_points`, `vector_points`, and analytics with regional skill segments plus embedding/extraction coverage.
- Produces: region-grouped divider-row Jobs, honest candidate Match decomposition, region-segmented Market bars and literal completeness footer, and a visually unified Admin console.

- [ ] Write failing behavior tests for region grouping/percentages, two candidates with non-uniform real score breakdowns, region segments, literal coverage copy, and authenticated admin routing.
- [ ] Implement Jobs grouped rows without card nesting and with extraction-tier labels when present.
- [ ] Render top-match point fields directly and validate that components sum to the displayed fit score.
- [ ] Render neutral regional segments and exact coverage data from the API.
- [ ] Align Admin with shared tokens, dense flat tables, and secure auth behavior.
- [ ] Run focused Node/Python tests, the full Python suite, and static acceptance greps.
- [ ] Start the local/deployed environment and use Browser to inspect Jobs, two Match personas, Market, and Admin at desktop and narrow widths; capture screenshots.
- [ ] Report each `docs/06_ui_refactor_spec.md` acceptance item with command or screenshot evidence.

