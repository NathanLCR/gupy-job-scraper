# Prompt: plan and start the SkillPulse production corrections

Use this prompt to start a fresh Codex task in the SkillPulse repository. The task does not need the preceding conversation, but it must read the repository files named below before proposing changes.

---

## Objective

Prepare and execute the correction work identified by deployed-site QA, starting with the release-blocking truthfulness and API-routing work.

The work is split into three approved specifications:

1. `docs/07_release_recovery_spec.md` — implement first;
2. `docs/08_admin_security_spec.md` — implement only after Spec 07 passes its local acceptance checkpoint;
3. `docs/09_accessibility_and_release_qa_spec.md` — implement after the release behavior is trustworthy and the operator boundary is fail-closed.

The broader Cloudflare backend migration remains in `docs/05_api_routing_fix_spec.md`. The UI direction remains in `docs/06_ui_refactor_spec.md`. Do not duplicate or silently replace either architecture.

## Production QA findings to reproduce

Testing of `https://skillpulse.pages.dev` on 2026-08-21 found:

- `GET /api/v1/jobs` returned SPA HTML instead of JSON;
- Jobs showed four cached example vacancies while claiming 1,490 live roles;
- Jobs search did not change those results;
- `POST /api/v1/match` returned HTTP 405, then the client generated a 91% match and three synthetic opportunities;
- Market showed exact metrics despite its API being unavailable;
- the job-details drawer was present in the accessibility tree before selection;
- sample-profile cards were pointer-clickable `div` elements without keyboard semantics;
- the complete admin surface was directly rendered without a login challenge;
- admin verification could accept an HTML 200 response as authenticated.

Treat the deployed behavior as defective until fresh evidence proves otherwise.

## Mandatory starting sequence

1. Read `AGENTS.md` completely.
2. Read Specs 07, 08, and 09 completely.
3. Read the relevant portions of Specs 05 and 06 so the correction work remains compatible with the selected D1/Worker architecture and product UI rules.
4. Inspect `git status`, the current diff, and recent commits. The working tree contains user-owned, uncommitted changes and partial routing/fallback tests. Preserve them.
5. Inspect at minimum:
   - `frontend/index.html`
   - `frontend/script.js`
   - `frontend/config.js`
   - `frontend/_redirects`
   - `frontend/_headers`
   - `frontend/api/404.json`
   - `frontend/admin.html`
   - `frontend/admin.js`
   - `config.py`
   - `api/v1/auth.py`
   - every mutating route in `app.py` and `api/v1/`
   - `tests/frontend_api_routing.test.js`
   - `tests/test_api_routing_fix.py`
   - existing API contract tests.
6. Use the `superpowers:writing-plans` skill to write an implementation plan for Spec 07 only. Do not edit production code until the user approves that plan.

## Implementation order after plan approval

### Checkpoint A — Spec 07: truthful release recovery

Use test-driven development:

- establish the focused Node and Python test baseline;
- add failing tests before correcting any missing behavior;
- make HTML, non-JSON, wrong-shape, failed, and stale responses render explicit unavailable states;
- distinguish valid empty datasets from API failures;
- eliminate automatic result fixtures and default scores from production paths;
- make sample profiles input-only until a valid API response exists;
- verify `config.js` load order and Pages `/api/*` JSON guarding;
- create a deterministic deploy-manifest procedure with reviewed asset hashes;
- verify locally in a browser with the API unavailable and with a local contract fixture.

Stop at the Spec 07 local acceptance checkpoint. Report results and request approval before any deployment or before beginning Spec 08.

### Checkpoint B — Spec 08: fail-closed operator security

After explicit approval:

- remove all default credentials and query-string authentication;
- make production startup fail without an explicit strong secret;
- separate operator assets from the public Pages artifact;
- implement opaque HttpOnly server sessions without returning the secret to JavaScript;
- inventory and protect every mutation and sensitive read;
- add origin/CSRF checks, login rate limiting, no-store headers, and audit events;
- verify the frontend remains locked for HTML 200, malformed JSON, network failure, 401, and 403;
- perform only read-only production security checks after deployment approval.

Stop and report the security acceptance checklist before beginning Spec 09.

### Checkpoint C — Spec 09: accessibility and release QA

After explicit approval:

- convert sample-profile controls to native buttons;
- make the drawer hidden and non-navigable initially;
- implement modal focus entry, focus trap, Escape close, content cleanup, and focus return;
- remove placeholder destinations and render only valid HTTPS job links;
- expose navigation and Market active states programmatically;
- add accurate status announcements;
- test 390×844, 768×1024, 1280×800, 1440×900, and 200% zoom;
- run the complete manual release matrix and produce the evidence package.

## Non-negotiable guardrails

- Do not call Groq, OpenRouter, Workers AI, Vectorize, or any other paid or metered AI service.
- Do not scrape, ingest, extract, embed, digest, initialize, migrate, delete, or export production data.
- Do not create Cloudflare resources or change account settings.
- Do not invoke admin mutations as tests.
- Do not deploy until the user approves the exact target and reviewed artifact.
- If any command or UI action might incur a charge, stop before it and ask.
- Use local fixtures for success-path testing.
- Preserve unrelated and overlapping user changes; never reset or overwrite the dirty worktree.
- Do not commit unless the user approves commits for the implementation task.
- Never claim completion without fresh test and browser evidence.

## Required handoff format at each checkpoint

Report:

1. files changed;
2. tests run with exact pass/fail totals;
3. browser scenarios exercised;
4. remaining spec acceptance items;
5. any production or cost-bearing action that still needs approval;
6. confirmation that no paid service or production mutation was invoked.

Start now by reading the specifications and repository state, then present the Spec 07 implementation plan for approval. Do not modify production code in the same turn as the plan.
