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

1. a syntactically valid `CF-Connecting-IP`, when Cloudflare proxy mode is configured;
2. the first syntactically valid address in `X-Forwarded-For`;
3. the immediate peer address.

Every value is parsed with the standard IP-address library and normalized before hashing. Invalid, empty, multi-value single-IP headers, zone identifiers, and non-IP strings are rejected rather than becoming distinct subjects.

`TRUSTED_PROXY_CIDRS` defaults to an empty list. Production deployment must explicitly configure the actual load balancer or reverse-proxy networks. Trusting `0.0.0.0/0` or `::/0` is rejected by configuration validation.

### 4.3 Origin exposure

Infrastructure should restrict the application origin to the selected proxy when practical. Application validation remains necessary because origin restrictions can be changed independently and local deployments may be direct.

## 5. Limit policy

The following defaults preserve current intent:

| Scope | Method and route group | Limit | Window |
|---|---|---:|---:|
| `public_search` | `POST /api/v1/jobs/search/*` | 60 | 60 seconds |
| `public_match` | `POST /api/v1/match` | 20 | 60 seconds |
| `public_explain` | `POST /api/v1/match/explain` | 5 | 60 seconds |
| `public_extract` | `POST /api/v1/extract` | 10 | 60 seconds |
| `operator_login_failure` | failed `POST /api/v1/admin/login` | 5 | 900 seconds |

Limits apply to route groups, not literal raw paths, so optional trailing slashes and path normalization cannot create extra buckets.

Successful operator login clears the subject's failure bucket. A failed login is recorded only after constant-time credential comparison. Requests already blocked by the failure limit do not compare credentials.

Authenticated operator mutations and health probes are not subject to the public limits. Separate operator-action throttles require evidence and a separate policy change.

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

- expensive public search, match, explain, and extract requests fail closed with HTTP `503`;
- operator login fails closed with HTTP `503`;
- already-authenticated operator requests continue to rely on normal authentication and authorization and are not blocked by this limiter failure;
- ordinary unmetered reads and health liveness remain available;
- readiness returns `503` once distributed rate limiting is enabled, because the configured protection cannot be enforced consistently.

The `503` response states that request protection is temporarily unavailable and includes a request ID. It does not silently allow quota-consuming work.

## 8. Configuration

Add and validate:

```dotenv
RATE_LIMIT_ENABLED=true
RATE_LIMIT_KEY_SALT=replace-with-at-least-32-random-characters
TRUSTED_PROXY_CIDRS=[]
TRUST_CLOUDFLARE_CONNECTING_IP=false
```

Existing per-scope limit settings remain supported. Production rejects:

- enabled rate limiting without Redis;
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

- Redis outage returns `503` on every protected expensive endpoint and login;
- ordinary versioned GET endpoints remain available;
- readiness becomes `503` while liveness remains `200`;
- no old in-memory store receives writes after the feature is enabled.

### 10.4 Security regression

From a direct, untrusted connection, send requests with a different `X-Forwarded-For` and `CF-Connecting-IP` value each time. The configured limit must still trigger based on the peer address.

## 11. Rollout and rollback

1. Provision and monitor Redis in the target environment.
2. Configure trusted proxy CIDRs and verify them from deployment network documentation.
3. Deploy the shared limiter with enforcement disabled and compare shadow decisions to current traffic.
4. Enable login enforcement, then expensive public endpoint enforcement.
5. Delete `_RATE_LIMIT_STORE`, `_FAILED_LOGINS`, and their helper functions in the same release that becomes authoritative.

Rollback disables the new middleware only by reverting the application release. Production configuration must not leave expensive endpoints enabled with no limiter. Redis keys expire naturally and require no destructive cleanup.
