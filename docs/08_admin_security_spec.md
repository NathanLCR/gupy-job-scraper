# SkillPulse — Operator Surface Security Specification

**Status:** Draft for review

**Date:** 2026-08-22

**Priority:** High

**Depends on:** `docs/07_release_recovery_spec.md`

**Related:** `docs/05_api_routing_fix_spec.md`, `docs/09_accessibility_and_release_qa_spec.md`

## 1. Purpose

Make every operator interface and administrative endpoint fail closed. A static frontend, API routing failure, missing environment variable, or invalid response must never reveal an apparently authenticated console or enable a mutation.

This specification covers authentication, authorization, operator asset exposure, session handling, and mutation protection. It does not redesign the admin interface.

## 2. Evidence and current risks

Production QA on 2026-08-21 found that `/frontend/admin.html` rendered the complete operator console without a login challenge. No mutation was invoked during testing.

The current source explains how this can occur:

- `frontend/admin.js` initializes `adminToken` with the literal fallback `skillpulse-admin-secret`;
- `checkAdminAuth()` treats any `res.ok` response as authenticated without requiring JSON or validating `{status: "authenticated"}`;
- the Pages SPA fallback can therefore return HTML 200 for `/api/v1/admin/verify`, which is accepted as authentication success;
- `frontend/admin.html` starts with the authentication overlay hidden and the operator workspace rendered;
- `config.py` and `api/v1/auth.py` contain the same production-capable default secret;
- the backend accepts credentials in query parameters;
- the login endpoint returns the credential as a token and sets a non-HttpOnly cookie;
- some mutating legacy and ingestion routes require a complete authorization audit.

## 3. Selected security architecture

### 3.1 Separate public and operator delivery

The public Cloudflare Pages artifact must not publish the operator HTML, JavaScript, or CSS. Direct requests to known operator asset paths return 404.

The operator console is served by the API application on the same origin under the Worker architecture described in `docs/05_api_routing_fix_spec.md`. `GET /operator/login` returns a login-only document. `GET /operator` requires a valid session cookie before returning the operator application shell. Operator JavaScript and CSS are served only from protected `/operator/assets/*` routes.

Until that protected host exists, the operator console remains unavailable in production. An unavailable admin console is safer than a public static console whose controls merely appear protected.

### 3.2 Browser authentication

The browser login flow exchanges an operator secret for an opaque, time-limited server session. The original secret is never returned to JavaScript and is never stored in `localStorage` or `sessionStorage`.

The session cookie must be:

- `HttpOnly`;
- `Secure` in production;
- `SameSite=Strict` on the selected same-origin operator architecture;
- scoped to `/`, because the same session authorizes both `/operator` and `/api/v1/admin/*`;
- expired after eight hours;
- rotated on successful login;
- invalidated server-side on logout.

If a cross-origin operator design is proposed later, it requires a separate reviewed CSRF and CORS design. This specification does not authorize `SameSite=None` as a shortcut.

### 3.3 Non-browser automation

CLI or trusted automation uses `Authorization: Bearer <secret>` only over HTTPS. Remove `X-Admin-Key` support and update its tests in the same change; retaining two header credential schemes adds no required capability.

Credentials in `token`, `admin_key`, or any other query parameter are prohibited because URLs leak into history, logs, analytics, and referrer data.

## 4. Configuration requirements

`ADMIN_API_KEY` has no default value. In production, application startup fails with a clear configuration error when:

- admin authentication is enabled and no secret is configured;
- the configured secret is shorter than 32 bytes of entropy-equivalent material;
- `ADMIN_AUTH_ENABLED` is false;
- debug mode is enabled.

Development tests must set an explicit test secret through the test environment. No source file, example response, frontend bundle, or committed config may contain a working credential.

Secret comparison uses `secrets.compare_digest` after normalizing inputs to the same type. Authentication failures return the same public message and status regardless of whether a credential was absent or incorrect.

Successful browser login generates 32 random bytes with `secrets.token_urlsafe(32)`. Store only a SHA-256 hash in an `admin_sessions` relation with `issued_at`, `expires_at`, `revoked_at`, and `last_seen_at`; place the raw token only in the HttpOnly cookie. The session relation is part of this security feature and uses the relational backend selected by `docs/05_api_routing_fix_spec.md`.

## 5. Authorization matrix

Public read-only endpoints:

- `GET /health`;
- `GET /api/v1/jobs` and approved job-detail/search reads;
- `GET /api/v1/analytics/overview` and approved public aggregates;
- `POST /api/v1/match` subject to public rate limiting and privacy rules.

Operator-only endpoints include every state-changing or sensitive operation, including:

- ingestion and scraping start/stop actions;
- extraction and batch processing;
- database initialization or migration;
- search-term create, update, and delete;
- raw payload and error-log access;
- task status containing internal errors;
- CSV exports that expose non-public fields;
- cache resets and maintenance operations.

Move operator-only routes under `/api/v1/admin/*`. Remove legacy mutation aliases such as `/scrape/start` and `/database/init` after the admin controller uses the protected namespace. This makes the cookie path and authorization boundary mechanically auditable.

Implementation must inventory all `POST`, `PUT`, `PATCH`, and `DELETE` routes in `app.py` and `api/v1/`. Every route must be classified explicitly as public or operator-only. An unclassified mutation fails the security review.

Authorization is enforced on the server route, never solely by hiding a button.

## 6. Fail-closed frontend behavior

The operator document starts in a locked state:

- the login surface is visible by default;
- the operator workspace uses `hidden` and is absent from the accessibility tree;
- no admin data request or action handler is initialized before verified authentication;
- a network error, timeout, HTML response, invalid JSON, wrong response shape, 401, or 403 keeps the workspace locked;
- verification succeeds only for JSON containing exactly the expected authenticated state;
- logout immediately hides and clears the workspace even if the network call fails.

The browser controller must not contain a default token. It must not read operator credentials from storage. Cookie-authenticated requests use `credentials: "same-origin"` on the selected same-origin architecture.

Buttons for mutation remain disabled while a request is in progress. Destructive or costly actions require a confirmation dialog that names the action and scope. This UI confirmation supplements server authorization; it does not replace it.

## 7. Session, CSRF, CORS, and rate limiting

- Operator routes allow only the operator origin; wildcard CORS is forbidden.
- State-changing cookie-authenticated requests validate `Origin` and reject missing or unexpected origins in production.
- Login permits at most five failed attempts per client IP in 15 minutes, followed by a 15-minute rejection window.
- Repeated failures produce HTTP 429 without revealing whether a key prefix was correct.
- Responses containing session cookies use `Cache-Control: no-store`.
- Authentication and mutation responses include `X-Content-Type-Options: nosniff`.
- Operator pages send `Content-Security-Policy: frame-ancestors 'none'`.

## 8. Audit logging

Record:

- login success and failure;
- logout;
- authorization failure;
- every operator mutation with action name, result, timestamp, request ID, and actor/session identifier;
- configuration refusal at startup.

Never record:

- raw credentials or hashes;
- cookies or authorization headers;
- CV/profile text;
- complete raw job payloads in authentication logs.

## 9. Testing requirements

### 9.1 Backend tests

Prove that:

- production startup fails without an explicit secret;
- the repository default secret is rejected;
- query-string credentials are rejected;
- invalid, missing, and expired sessions receive 401;
- every inventoried mutation requires operator authorization;
- public read endpoints remain accessible;
- login sets an opaque HttpOnly cookie and does not return the secret;
- logout invalidates the session;
- unexpected origins are rejected on cookie-authenticated mutations;
- rate limiting activates after the configured number of failed logins;
- responses do not echo credentials.

### 9.2 Frontend tests

Prove that:

- the console is locked before verification;
- HTML 200 from `/verify` does not authenticate;
- malformed or wrong-shape JSON does not authenticate;
- only the exact valid JSON contract unlocks the workspace;
- authentication failure triggers no overview or mutation request;
- logout relocks the interface even when its request fails;
- no default secret or storage access exists in the production controller.

### 9.3 Production checks

Production checks are read-only unless separately approved:

- known public admin asset URLs return 404 on Pages;
- the protected operator URL returns a login challenge or an access denial;
- unauthenticated API verification returns 401 JSON, never HTML 200;
- no ingestion, extraction, initialization, deletion, or export action is invoked during the check.

## 10. Cost and safety guardrails

- Do not run ingestion, scraping, extraction, embedding, or database initialization while implementing or testing authentication.
- Do not create Cloudflare Access policies, domains, Workers, or other account resources without explicit approval.
- Do not use paid identity, email, SMS, AI, or CAPTCHA services.
- Use local sessions and fixtures for automated tests.
- Do not place a real operator secret in a command, test output, screenshot, URL, or committed file.
- Do not deploy without explicit user approval.

## 11. Acceptance checklist

- [ ] Public Pages no longer publishes operator assets.
- [ ] Operator UI is locked by default and fails closed.
- [ ] No frontend or backend default admin secret exists.
- [ ] Query-string credentials are rejected.
- [ ] Browser JavaScript never receives or stores the operator secret after login.
- [ ] Session cookies are opaque, HttpOnly, time-limited, and invalidated on logout.
- [ ] Every mutating or sensitive endpoint has server-side authorization.
- [ ] CSRF, CORS, login rate limiting, and no-store behavior are tested.
- [ ] Read-only production security checks pass.
- [ ] No administrative mutation was used as a smoke test.

## 12. Out of scope

- multi-user roles or organization management;
- OAuth, SSO, email login, or account recovery;
- Cloudflare Access provisioning;
- public frontend routing and truthfulness, governed by `docs/07_release_recovery_spec.md`;
- visual redesign of the admin console;
- database or vector-store migration.
