# Distributed Rate Limiting and Trusted Client Identity Design

**Status:** Approved design; implementation not started

**Date:** 2026-08-28

**Program:** [`2026-08-28-postgresql-remediation-program-design.md`](2026-08-28-postgresql-remediation-program-design.md)

**Priority:** Phase 3

**Shared store:** Redis

## 1. Purpose

Replace process-local, spoofable request counters with limits shared by every Uvicorn worker and application instance. Protect paid or quota-bound AI operations and the operator login surface without trusting arbitrary forwarding headers.

## 2. Current failure modes

- `_RATE_LIMIT_STORE` and `_FAILED_LOGINS` exist only in one Python process.
- two Uvicorn workers therefore enforce two independent allowances.
- restarts erase counters, and horizontal scaling multiplies the effective limit.
- callers can supply `CF-Connecting-IP` or `X-Forwarded-For` directly when the origin is reachable.
- arbitrary spoofed identities create unbounded in-memory dictionary keys.
- public and login enforcement use separate implementations and different retention behavior.

## 3. Selected architecture

### 3.1 Shared limiter service

Create one Redis-backed rate-limit service used by public endpoints and operator login. The service exposes one conceptual operation:

```text
check(scope, subject, limit, window_seconds) -> decision
```

The decision contains:

- `allowed: bool`
- `limit: int`
- `remaining: int`
- `retry_after_seconds: int`
- `reset_after_seconds: int`

All workers use the `REDIS_URL` already present in application configuration. Celery and rate limiting may share a Redis deployment but use distinct key prefixes and, where operationally available, a distinct Redis database number.

### 3.2 Algorithm

Use an atomic Redis sorted-set sliding window implemented as a Lua script:

1. remove members with timestamps older than the window;
2. count remaining members;
3. if the count is below the limit, add a unique request member;
4. set key expiry to the window plus 60 seconds;
5. return allowed, remaining, and the oldest retained timestamp needed for retry calculation.

The member identifier combines the current millisecond timestamp with a random request nonce so concurrent requests cannot overwrite each other.

The script is the sole read-modify-write boundary. A Python sequence of separate `ZREMRANGEBYSCORE`, `ZCARD`, and `ZADD` calls is not acceptable because concurrent workers could all pass the same limit.

### 3.3 Key design and retention

Redis keys use:

```text
skillpulse:ratelimit:v1:{scope}:{subject_digest}
```

`subject_digest` is an HMAC-SHA-256 of the normalized client IP using `RATE_LIMIT_KEY_SALT`. Raw IP addresses are not stored in Redis keys or logs.

Production requires a non-placeholder salt of at least 32 random characters. Key expiry guarantees bounded retention. The application never enumerates rate-limit keys during a request.

## 4. Trusted client identity

### 4.1 Direct requests

When the immediate TCP peer is not in `TRUSTED_PROXY_CIDRS`, client identity is `request.client.host`. The application ignores `CF-Connecting-IP`, `True-Client-IP`, `Forwarded`, and `X-Forwarded-For` completely.

### 4.2 Proxied requests

When the immediate peer belongs to `TRUSTED_PROXY_CIDRS`, resolve identity in this order:

1. a syntactically valid single-value `CF-Connecting-IP`, when `TRUST_CLOUDFLARE_CONNECTING_IP` is set. Cloudflare replaces this header on every request, so it is the trustworthy value on a Cloudflare deployment.
2. otherwise, the **right-most** address in `X-Forwarded-For` that is *not* itself in `TRUSTED_PROXY_CIDRS` — i.e. walk the list from the end, skip entries that are trusted-proxy hops, and take the first remaining address. Trusted proxies (Cloudflare, ALBs, nginx) **append** the real client and forward whatever the client already sent, so the left-most entry is attacker-controlled and must never be used.
3. the immediate peer address.

Every value is parsed with the standard IP-address library and normalized before hashing. Invalid, empty, multi-value single-IP headers, zone identifiers, and non-IP strings are rejected rather than becoming distinct subjects. If no non-proxy address remains after step 2, fall through to the peer address (step 3) and emit `client_identity_peer_fallback`.

`TRUSTED_PROXY_CIDRS` defaults to an empty list. Production deployment must explicitly configure the actual load balancer or reverse-proxy networks. Trusting `0.0.0.0/0` or `::/0` is rejected by configuration validation.

### 4.3 Origin exposure

Infrastructure should restrict the application origin to the selected proxy when practical. Application validation remains necessary because origin restrictions can be changed independently and local deployments may be direct.

## 5. Limit policy

The following defaults preserve current intent:

| Scope | Method and route group | Auth | Limit | Window |
|---|---|---|---:|---:|
| `public_search` | `POST /api/v1/jobs/search/*` | public | 60 | 60 seconds |
| `public_match` | `POST /api/v1/match` | public | 20 | 60 seconds |
| `ai_explain` | `POST /api/v1/match/explain` | operator | 5 | 60 seconds |
| `ai_extract` | `POST /api/v1/extract` | operator | 10 | 60 seconds |
| `operator_login_failure` | failed `POST /api/v1/admin/login` | public | 5 | 900 seconds |

`/api/v1/match/explain` and `/api/v1/extract` are already operator-authenticated in the current code (`api/v1/router.py` mounts the extract router under `require_admin_auth`; `match.py` guards `/explain`). They are still metered because they call paid LLM/embedding providers and a compromised or shared operator credential must not be able to exhaust that quota. These two scopes are the **explicit exception** to the "authenticated requests are exempt" rule below — they are keyed on client identity exactly like public scopes. The finding they resolve (program spec §1.4) is precisely that "public and operator" AI-cost limits were both process-local.

Limits apply to route groups, not literal raw paths, so optional trailing slashes and path normalization cannot create extra buckets. Because these two scopes run in middleware ahead of route auth, an unauthenticated caller that would be `401`'d still consumes the identity's allowance for that scope; that is acceptable (it protects the same quota) and documented.

Successful operator login clears the subject's failure bucket. A failed login is recorded only after constant-time credential comparison. Requests already blocked by the failure limit do not compare credentials.

Apart from `ai_explain` and `ai_extract`, authenticated operator mutations and health probes are not subject to these limits. Separate operator-action throttles require evidence and a separate policy change.

## 6. Response contract

Allowed limited responses include:

- `RateLimit-Limit`
- `RateLimit-Remaining`
- `RateLimit-Reset`

Rejected requests return HTTP `429`, `Content-Type: application/json`, `Cache-Control: no-store`, and `Retry-After`:

```json
{
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after_seconds": 42,
  "request_id": "..."
}
```

The response does not reveal the resolved IP, digest, proxy decision, Redis key, credential state, or current count from another scope.

## 7. Dependency failure policy

When Redis is unavailable or the atomic script fails:

- requests in the `public_search`, `public_match`, `ai_explain`, and `ai_extract` scopes fail closed with HTTP `503`;
- operator login fails closed with HTTP `503`;
- already-authenticated operator requests (other than `ai_explain` / `ai_extract`) continue to rely on normal authentication and authorization and are not blocked by this limiter failure;
- ordinary unmetered reads and health liveness remain available.

**Readiness is not gated on Redis for traffic admission.** A brief Redis outage must not pull every instance out of rotation and take down unmetered reads too — that would convert a limiter degradation into a full outage. Instead:

- `/health/ready` stays `200` during a Redis outage and reports `dependencies.redis` as `"degraded"` (database still `"connected"`);
- the per-request fail-closed `503` above is what actually protects quota-consuming work;
- observability alerts (§9) fire on sustained Redis errors so operators intervene.

The `503` response states that request protection is temporarily unavailable and includes a request ID. It does not silently allow quota-consuming work.

## 8. Configuration

Add and validate:

```dotenv
RATE_LIMIT_ENABLED=true
RATE_LIMIT_SHADOW=false
RATE_LIMIT_KEY_SALT=replace-with-at-least-32-random-characters
TRUSTED_PROXY_CIDRS=[]
TRUST_CLOUDFLARE_CONNECTING_IP=false
```

`RATE_LIMIT_SHADOW=true` computes and logs decisions without returning `429`/`503`; it is the intermediate rollout state (§11) and is not a valid long-term production setting.

`REDIS_URL` becomes `Optional[str] = None` (runtime spec §4.3) so "enabled rate limiting without Redis" is a representable, rejected state rather than a silent default. Docker Compose and both env examples set it explicitly.

Existing per-scope limit settings remain supported. Existing setting names `RATE_LIMIT_SEARCH_RPM`, `RATE_LIMIT_MATCH_RPM`, `RATE_LIMIT_EXPLAIN_RPM`, `RATE_LIMIT_EXTRACT_RPM` continue to feed scopes `public_search`, `public_match`, `ai_explain`, `ai_extract` respectively. Production rejects:

- enabled rate limiting with `REDIS_URL` unset;
- enabled rate limiting where Redis is set but unreachable at startup (bounded ping);
- a missing, placeholder, or short HMAC salt;
- invalid CIDR entries;
- universal trusted-proxy networks;
- Cloudflare-header trust without at least one trusted proxy CIDR;
- zero or negative limits/windows.

Development may disable rate limiting explicitly. Production may not disable it while public AI endpoints are enabled.

## 9. Observability

Emit structured metrics and logs for:

- allowed requests by scope;
- rejected requests by scope;
- Redis errors;
- trusted-proxy header rejection;
- fallback to peer address;
- rate-limit decision latency.

Logs include the first 12 hexadecimal characters of the HMAC digest only when correlation is required. They never include raw IPs, forwarding-header contents, résumé bodies, API keys, or session cookies.

Alert when:

- Redis errors occur for more than one minute;
- `503` limiter failures exceed 1% of protected requests over five minutes;
- `429` responses increase to more than five times the seven-day baseline for a scope.

## 10. Tests and acceptance criteria

### 10.1 Identity tests

- an untrusted peer cannot change its subject with any forwarding header;
- a trusted peer can supply one valid configured header;
- malformed and multi-value headers are rejected;
- IPv4, IPv6, and IPv4-mapped IPv6 values normalize consistently;
- universal trusted-proxy CIDRs fail configuration validation.

### 10.2 Atomicity and distribution tests

- concurrent requests from two independent application instances share one allowance;
- exactly `limit` requests pass in one window and the next receives `429`;
- a process restart does not reset the allowance;
- expired keys disappear without cleanup jobs;
- successful operator login clears only that subject's failure bucket;
- different scopes do not consume one another's allowance.

These tests run against a real Redis service in integration CI. Unit tests may use a fake Redis client for error mapping, but a fake is not sufficient evidence for Lua atomicity.

### 10.3 Failure tests

- Redis outage returns `503` on every `public_*` / `ai_*` scope and on login;
- ordinary versioned GET endpoints remain available;
- readiness stays `200` with `dependencies.redis == "degraded"` while liveness remains `200` (readiness is not gated on Redis for admission — §7);
- no old in-memory store receives writes after the feature is enabled.

### 10.4 Security regression

- From a direct, untrusted connection, send requests with a different `X-Forwarded-For` and `CF-Connecting-IP` value each time. The configured limit must still trigger based on the peer address.
- From a **trusted** proxy peer, send `X-Forwarded-For: <attacker-chosen>, <real-client>` (proxy-appended form) on each request with a rotating attacker-chosen left-most value. The subject must resolve to `<real-client>` (right-most non-proxy entry) so the limit still triggers.
- With `TRUST_CLOUDFLARE_CONNECTING_IP=true`, a trusted peer supplying only `X-Forwarded-For` (no `CF-Connecting-IP`) still resolves to the right-most non-proxy entry, not the left-most.

## 11. Rollout and rollback

1. Provision and monitor Redis in the target environment; set `REDIS_URL` explicitly.
2. Configure `TRUSTED_PROXY_CIDRS` (for a Cloudflare-fronted deployment, the Cloudflare edge ranges) and `TRUST_CLOUDFLARE_CONNECTING_IP`, verified against deployment network documentation.
3. Deploy the shared limiter in shadow mode (`RATE_LIMIT_SHADOW=true`): resolve identity and compute decisions, log them via the §9 events, but enforce nothing. Compare shadow decisions to current traffic.
4. Turn off shadow mode so enforcement takes effect — login scope first, then the `public_*` / `ai_*` scopes. `RATE_LIMIT_ENABLED` remains the hard on/off; `RATE_LIMIT_SHADOW` is the observe-only intermediate state.
5. Delete `_RATE_LIMIT_STORE`, `_FAILED_LOGINS`, and their helper functions in the same release that becomes authoritative. The operator-security test suite imports `_FAILED_LOGINS` at module scope and clears it in fixtures — those imports/fixtures and the old `429` message assertions are rewritten in this step.

Rollback is `RATE_LIMIT_ENABLED=false` (takes effect without redeploy) and/or reverting the release. Production configuration must not leave `public_*` / `ai_*` scopes reachable with enforcement permanently disabled. Redis keys expire naturally and require no destructive cleanup.
