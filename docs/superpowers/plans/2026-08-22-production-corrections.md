# Production Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Close the confirmed security and accessibility gaps, publish a truthful zero-cost Cloudflare Pages artifact, and verify production against Specs 07–09.

**Architecture:** Cloudflare Pages continues to serve only frontend/, with an empty API_BASE_URL and a JSON 404 boundary for /api/*. FastAPI keeps the operator application outside the public static root, exposes a login-only document publicly, and session-gates the workspace, assets, sensitive reads, extraction, persistence, and normalization routes.

**Tech Stack:** FastAPI, SQLAlchemy, vanilla HTML/CSS/JavaScript, Node test runner, Playwright Chromium, pytest, Cloudflare Pages/Wrangler.

**Spec:** docs/07_release_recovery_spec.md, docs/08_admin_security_spec.md, docs/09_accessibility_and_release_qa_spec.md

## Global Constraints

- Do not call Groq, OpenRouter, Workers AI, Vectorize, scraping, ingestion, extraction, embedding, digest, or database-maintenance actions.
- Do not create or resize Cloudflare resources; deploy only the existing skillpulse Pages project.
- Deploy only frontend/, after a clean manifest is generated from a committed worktree.
- Preserve existing user work and do not discard unrelated changes.

---

### Task 1: Close the sensitive API surface

**Files:**
- Modify: tests/test_spec08_admin_security.py
- Modify: api/v1/router.py
- Modify: api/v1/match.py
- Modify: api/v1/analytics.py
- Modify: app.py
- Modify: api/v1/auth.py

**Interfaces:**
- Consumes: require_admin_auth(request).
- Produces: 401 JSON for unauthenticated extraction, candidate-profile, normalization, raw-posting, legacy search-term, and stats access; structured operator audit events; nosniff security headers.

- [ ] **Step 1: Write failing authorization and security-header tests**

Add literal request/response assertions covering:

    POST /api/v1/extract
    POST /api/v1/match/profile
    GET /api/v1/match/profile/1
    POST /api/v1/analytics/normalize
    GET /job-posts
    GET /search-terms
    GET /stats

Assert 401, JSON content type, Cache-Control: no-store, and X-Content-Type-Options: nosniff without invoking endpoint bodies.

- [ ] **Step 2: Run the focused tests and confirm the expected authorization failures**

Run: ./.venv/bin/pytest -q tests/test_spec08_admin_security.py

Expected: the new cases fail because the listed routes are currently public and/or lack nosniff.

- [ ] **Step 3: Add minimal route dependencies and safe audit metadata**

Protect the extraction router at inclusion, add route-level protection to Match profile/explain and analytics normalization, protect legacy raw/search-term/stats reads, set a non-secret actor identifier on authenticated requests, and add global nosniff plus operator mutation audit output without logging bodies, headers, cookies, or credentials.

- [ ] **Step 4: Run focused and full Python tests**

Run: ./.venv/bin/pytest -q tests/test_spec08_admin_security.py

Run: ./.venv/bin/pytest -q

Expected: all tests pass and no endpoint body is executed by unauthenticated regression cases.

### Task 2: Separate login-only and session-gated operator delivery

**Files:**
- Create: operator/login.html
- Modify: operator/admin.html
- Modify: operator/admin.js
- Modify: app.py
- Modify: frontend/_redirects
- Modify: tests/test_spec08_admin_security.py
- Modify: tests/admin_frontend_security.test.js

**Interfaces:**
- Produces: public GET /operator/login; protected GET /operator; protected GET /operator/assets/{admin.js|admin.css}.
- Browser login posts {key} to /api/v1/admin/login and redirects to /operator; workspace handlers initialize only after exact JSON verification.

- [ ] **Step 1: Write failing backend and browser tests**

Assert that /operator/login contains a password form but no admin-app-layout, /operator and its assets return 401 without authentication, an authenticated session can retrieve them, old obscured/admin paths return 404, and initAdminActions() is not called before checkAdminAuth() succeeds.

- [ ] **Step 2: Run focused tests and confirm they fail for the existing combined public document**

Run: ./.venv/bin/pytest -q tests/test_spec08_admin_security.py

Run: node --test tests/admin_frontend_security.test.js

- [ ] **Step 3: Implement the distinct operator entry flow**

Serve an inline-styled/scripted login-only page. Gate the workspace and known assets with Depends(require_admin_auth). Keep the workspace hidden during session verification; redirect to /operator/login on verification failure; initialize navigation, actions, and data only after verification succeeds.

- [ ] **Step 4: Run focused security tests**

Run: ./.venv/bin/pytest -q tests/test_spec08_admin_security.py

Run: node --test tests/admin_frontend_security.test.js

Expected: all focused tests pass.

### Task 3: Complete Spec 09 error semantics and drawer cleanup

**Files:**
- Modify: frontend/index.html
- Modify: frontend/script.js
- Modify: tests/spec09_accessibility_and_release_qa.test.js
- Modify: tests/browser_release_acceptance.test.js

**Interfaces:**
- Produces: assertive unavailable alerts; matcher-resume-error connected to the textarea; cleared drawer-specific content and URL after close.

- [ ] **Step 1: Write failing browser assertions**

Assert unavailable states use role=alert, empty Match submit sets aria-invalid=true and exposes the referenced error element, typing clears the error, and drawer close empties title/company/location/workplace/skills/description/date/score and removes the link destination.

- [ ] **Step 2: Run browser tests and confirm expected failures**

Run: node --test tests/spec09_accessibility_and_release_qa.test.js tests/browser_release_acceptance.test.js

- [ ] **Step 3: Implement minimal accessible behavior**

Use one inline alert per failure, remove duplicate toast/live announcements for the same error, add and clear the field-level validation state, and centralize drawer-content clearing for initial and close states.

- [ ] **Step 4: Run all Node and browser tests**

Run: node --test tests/frontend_api_routing.test.js tests/admin_frontend_security.test.js tests/browser_release_acceptance.test.js tests/spec09_accessibility_and_release_qa.test.js

Expected: all tests pass in real Chromium.

### Task 4: Prepare, deploy, and smoke-test the exact Pages artifact

**Files:**
- Modify: .gitignore only if required to exclude runtime logs.
- Modify: docs/07_release_recovery_spec.md, docs/08_admin_security_spec.md, and docs/09_accessibility_and_release_qa_spec.md only to make checklist status truthful.
- Generate for review: manifest output from scripts/generate_deploy_manifest.py.

**Interfaces:**
- Consumes: committed frontend/ artifact.
- Produces: https://skillpulse.pages.dev serving the reviewed hashes and honest unavailable states.

- [ ] **Step 1: Run the complete pre-deploy gate**

Run git diff --check, both JavaScript syntax checks, all four Node suites, and the full pytest suite.

- [ ] **Step 2: Review and commit the scoped working tree**

Exclude runtime logs and secrets. Inspect git diff --stat, git status, and the deploy manifest. Commit the reviewed implementation so the manifest reports dirty: false.

- [ ] **Step 3: Verify Wrangler authentication and deploy the existing Pages project**

Use the current documented Wrangler Pages deploy command for the existing skillpulse project and the frontend/ directory. Do not create a project or resource.

- [ ] **Step 4: Run read-only production smoke checks**

Verify /frontend/config.js is JavaScript, /api/v1/jobs is JSON 404 rather than HTML, Match/Jobs/Market show truthful unavailable states, /frontend/admin.html and /operator are unavailable, no fixture companies or synthetic scores render, and deployed asset hashes match the reviewed manifest.
