# SkillPulse — Production Release Recovery Specification

**Status:** Draft for review

**Date:** 2026-08-22

**Priority:** Release blocker

**Depends on:** `docs/05_api_routing_fix_spec.md` Phase 0 and the completed D1 Python read spike

**Related:** `docs/08_admin_security_spec.md`, `docs/09_accessibility_and_release_qa_spec.md`

## 1. Purpose

Restore an honest, testable production release at `https://skillpulse.pages.dev` before continuing the broader D1 and Vectorize migration.

The public site currently fails its live API requests but presents cached or generated results as if they came from the active dataset. This specification makes transport failure visible, prevents HTML SPA responses from being accepted as API data, and establishes a repeatable deployment verification process.

This is a release-recovery specification, not the full Cloudflare backend migration. The D1 relational migration and Vectorize work remain governed by `docs/05_api_routing_fix_spec.md`.

## 2. Evidence and current state

Production QA on 2026-08-21 established:

- `GET /api/v1/jobs?page=1&page_size=5` returned the SPA HTML document with HTTP 200 instead of JSON.
- the Jobs view logged `Unexpected token '<'` and displayed four cached example vacancies while claiming 1,490 roles;
- a search for `Python` still displayed the same four cached vacancies;
- `POST /api/v1/match` returned HTTP 405, after which the client generated a 91% result and three synthetic opportunities;
- Market displayed exact counts and percentages while its live API was unavailable;
- the deployed page did not load the repository's current `frontend/config.js` before its controller;
- the current working tree already contains partial corrections, including JSON content-type validation, explicit unavailable states, `frontend/config.js`, and a Pages `/api/*` guard. These changes are uncommitted and were not present in the tested deployment.

The implementation must audit and test those local changes. It must not assume they are correct merely because they exist.

## 3. Selected release architecture

### 3.1 Before the production API exists

Cloudflare Pages serves the public frontend only. `window.API_BASE_URL` remains empty, and every same-origin `/api/*` request is terminated by a JSON 404 rule before the SPA fallback.

The UI displays a clear unavailable state. It must not substitute jobs, metrics, scores, companies, skill gaps, or role counts.

This state is acceptable as an emergency truthful release: functionality is visibly unavailable, but the product no longer misrepresents generated data as live market evidence.

### 3.2 After the production API exists

`frontend/config.js` contains the reviewed HTTPS origin of the deployed API. The file loads before `frontend/script.js` and is not cached longer than the release HTML.

The public client may render results only when all of the following are true:

1. the HTTP response is successful;
2. the final response content type includes `application/json`;
3. the response body satisfies the expected endpoint contract;
4. the request was not redirected to an HTML or login document.

The eventual same-origin Worker and D1 architecture remains the preferred target in `docs/05_api_routing_fix_spec.md`. This recovery specification does not create an interim paid service or revive the failed Hyperdrive path.

## 4. Product truthfulness requirements

### 4.1 Jobs

The Jobs view consumes `GET /api/v1/jobs` and expects the existing `JobListResponse` shape:

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total_items": 0,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

These fields and bounds are the `PaginationMeta` contract in `schemas/common.py` and must be contract-tested.

On transport, content-type, parse, timeout, or schema failure:

- clear all previously rendered results;
- replace the result count with `Unavailable` rather than a number;
- show `Live data unavailable right now. No cached vacancies are being shown.`;
- preserve the user's query and filters so the request can be retried;
- do not render any fixture company or vacancy.

A successful response with `items: []` is not an error. It renders `No vacancies matched these filters.` and a count of zero.

### 4.2 Candidate matching

The Match view consumes `POST /api/v1/match` and expects the existing `CandidateMatchResponse` contract.

On failure:

- hide and clear the result section;
- show `Live matching is unavailable right now. Your profile was not scored.`;
- never manufacture `fit_score`, component points, competencies, missing skills, or opportunities;
- never use default values such as 88 or 92 when a response omits a score;
- preserve the profile text locally in the form, but do not persist it remotely unless the user invokes a separate, explicit save action.

Sample profiles remain allowed only as clearly labeled input examples. Selecting one may populate the form, but it must not claim a market result unless the live API returns a valid response. A sample selector must not silently trigger a paid or mutating request.

### 4.3 Market

The Market view consumes `GET /api/v1/analytics/overview` and expects `SkillAnalyticsResponse`.

On failure:

- set all headline metrics to `Unavailable`;
- clear all distribution bars and counts;
- display a single status message stating that live market aggregates could not be loaded;
- remove or replace `Data updated recently` with `Update status unavailable`;
- never retain metrics from a previous successful request after a later request fails.

### 4.4 Demonstration data

Input examples may exist in source code. Output fixtures must exist only in tests or in a separately labeled demo route that is not presented as production data.

The production controller must not contain automatic result fallbacks. Static scans must reject known fixture names from production output paths, including `VectorAI Labs`, `FinScale Technologies`, `Scale AI Systems`, and `Cognitive Retrieval Labs`.

## 5. API transport and routing requirements

Implement one shared JSON request helper for the public client. It must:

- compose URLs from a normalized `window.API_BASE_URL` without double slashes;
- use an explicit timeout with `AbortController`;
- set Fetch `redirect: "error"` so API redirects never become renderable data;
- reject non-2xx responses with the status code in the internal error;
- reject a missing or non-JSON content type before calling `response.json()`;
- reject redirects when the final URL is outside the configured API origin or resolves to a known frontend document;
- validate each endpoint's minimal required fields before rendering;
- expose a stable error category to UI renderers without exposing stack traces or credentials to users.

Cloudflare Pages routing must apply in this order:

1. static assets;
2. the explicit SPA view routes `/match`, `/jobs`, `/market`, and `/how-it-works`;
3. `/api/*` to a small JSON 404 asset with HTTP 404 when no API is mounted;
4. the SPA catch-all to `index.html`.

`frontend/api/404.json` must have `Content-Type: application/json; charset=utf-8` and contain no secret or internal hostname.

## 6. Deployment artifact requirements

The Pages build must have one documented source directory. The selected output is the repository's `frontend/` directory, preserving `_redirects`, `_headers`, `config.js`, and `api/404.json`.

Before any production deployment, generate and inspect a deploy manifest containing:

- SHA-256 hashes for `index.html`, `script.js`, `style.css`, `config.js`, `_redirects`, `_headers`, and `api/404.json`;
- the Git commit and dirty-worktree status;
- the configured API origin with credentials and query parameters removed;
- the intended Cloudflare Pages project and branch.

Do not deploy from an unspecified directory or from an artifact whose hashes were not inspected.

To prevent stale controllers after release:

- `index.html` and `config.js` use `Cache-Control: no-cache`;
- versioned immutable caching is allowed only for assets whose URL changes with content;
- `script.js` and `style.css` must not use a one-day cache unless their URLs contain a content hash or release version.

## 7. Error handling and observability

Client errors must be observable without leaking candidate text:

```text
event=public_api_failure
view=jobs|match|market
endpoint=/api/v1/...
category=http|content_type|timeout|schema|network
status=<integer-or-null>
```

Never log CV/profile text, admin credentials, cookies, authorization headers, or full query strings.

The production smoke check must treat any console warning from a core request as a failed release unless that warning is explicitly allowlisted and documented.

## 8. Testing requirements

### 8.1 Automated tests

Add or extend Node tests to prove:

- an HTML 200 response produces the unavailable state for Jobs, Match, and Market;
- an HTTP 404/405/500 produces the unavailable state;
- invalid JSON and valid JSON with the wrong shape are rejected;
- empty valid datasets render honest empty states;
- previous successful data is cleared after a failed refresh;
- sample profile selection does not generate result output without a successful API response;
- no production fallback fixture is rendered.

Add or extend Python tests to prove:

- `config.js` loads before each controller;
- the Pages `/api/*` rule precedes the SPA catch-all;
- `api/404.json` is valid JSON and returns the intended content type in the served artifact;
- the API contracts used by the frontend match the Pydantic response models.

### 8.2 Local browser acceptance

With the API deliberately unavailable:

- Jobs, Match, and Market show unavailable states;
- no synthetic outputs appear;
- no uncaught exception is logged;
- navigation, retry, and form reset remain usable.

With a local fixture API returning contract-valid JSON:

- Jobs filters alter the request and rendered results;
- Match renders only server-provided scores and point components;
- Market renders only server-provided totals and distributions.

### 8.3 Production acceptance

Production deployment requires explicit user approval. After approval and deployment, verify:

- `/frontend/config.js` is the reviewed version;
- `/api/v1/jobs?page=1&page_size=5` returns JSON or an honest JSON 404, never `index.html`;
- the three public views behave consistently with the actual API state;
- no fallback companies or generated scores appear;
- two consecutive requests produce the same routing behavior;
- browser console has no core-flow error or warning;
- the deployed asset hashes match the reviewed manifest.

## 9. Cost and operational guardrails

- Do not invoke Groq, OpenRouter, Workers AI, Vectorize, or any other metered AI service while implementing or testing this specification.
- Do not run scraping, ingestion, extraction, embedding, or digest jobs.
- Do not create or resize Cloudflare resources.
- Use local fixtures and existing data for tests.
- Do not deploy until the user explicitly approves the exact artifact and target.
- If Cloudflare indicates that an action may incur charges, stop before the action and report it.

## 10. Acceptance checklist

- [ ] HTML SPA responses cannot be parsed as API success.
- [ ] Jobs never displays cached or fixture vacancies after live failure.
- [ ] Match never displays generated scores or opportunities after live failure.
- [ ] Market never displays stale or seeded metrics after live failure.
- [ ] Empty valid responses are distinct from unavailable responses.
- [ ] `config.js` loads before both public and admin controllers.
- [ ] Pages `/api/*` returns JSON 404 before the SPA fallback when no API is mounted.
- [ ] Deploy artifacts are hashed and reviewed.
- [ ] Local automated and browser acceptance passes.
- [ ] Production deployment and smoke testing occur only after explicit approval.

## 11. Out of scope

- D1 schema migration and production data import;
- Vectorize index creation or Workers AI embedding generation;
- scraper or extraction pipeline changes;
- admin authentication implementation, governed by `docs/08_admin_security_spec.md`;
- accessibility and responsive corrections, governed by `docs/09_accessibility_and_release_qa_spec.md`;
- visual redesign beyond the minimum unavailable and empty states.
