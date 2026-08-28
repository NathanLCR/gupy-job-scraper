# Distributed Rate Limiting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce spoof-resistant request limits consistently across every worker and instance using Redis and explicit trusted-proxy configuration.

**Architecture:** A dedicated client-identity resolver accepts forwarding headers only from configured proxy networks. A Redis Lua script performs the complete sliding-window decision atomically and stores only HMAC-derived subjects. FastAPI public middleware and operator login share the service; protected expensive operations fail closed when Redis is unavailable.

**Tech Stack:** Python 3.11+, FastAPI, Redis 5 client, Redis Lua scripting, `ipaddress`, HMAC-SHA-256, pytest, real Redis integration tests, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-28-distributed-rate-limiting-design.md`

## Global Constraints

- Raw IP addresses, forwarding-header values, credentials, session tokens, and résumé bodies must not appear in Redis keys or logs.
- `TRUSTED_PROXY_CIDRS` defaults to empty and may not contain `0.0.0.0/0` or `::/0`.
- One atomic Lua script owns prune/count/add/expiry; separate Redis commands are not an acceptable decision boundary.
- Protected expensive endpoints and operator login fail closed with `503` when Redis cannot enforce limits.
- Health liveness and ordinary unmetered reads remain available during a Redis outage.
- Existing limit setting names and default allowances remain stable unless the spec explicitly changes them.

---

### Task 1: Add validated rate-limit and trusted-proxy settings

**Files:**
- Modify: `config.py:45-67,67-100`
- Modify: `.env.example`
- Modify: `.env.production.example`
- Create: `tests/test_rate_limit_config.py`
- Test: `tests/test_rate_limit_config.py`

**Interfaces:**
- Consumes: `Settings.validate_runtime_config()` from the runtime implementation plan.
- Produces: `RATE_LIMIT_KEY_SALT`, `TRUSTED_PROXY_CIDRS`, `TRUST_CLOUDFLARE_CONNECTING_IP`, parsed `trusted_proxy_networks`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_trusted_proxy_defaults_to_empty():
    settings = Settings(_env_file=None)
    assert settings.get_trusted_proxy_networks() == ()

@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "::/0", "not-a-cidr"])
def test_production_rejects_unsafe_proxy_cidrs(cidr):
    settings = production_settings(TRUSTED_PROXY_CIDRS=json.dumps([cidr]))
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_CIDRS"):
        settings.validate_runtime_config()
```

Add cases for missing/short/placeholder salt, enabled limiter without Redis, nonpositive limits, and Cloudflare-header trust without a trusted CIDR.

- [ ] **Step 2: Run tests and verify the settings are absent**

Run: `.venv/bin/python -m pytest tests/test_rate_limit_config.py -v`

Expected: FAIL because the new settings/parser do not exist.

- [ ] **Step 3: Implement typed settings and parser**

```python
REDIS_URL: Optional[str] = None          # was: "redis://localhost:6379/0"
RATE_LIMIT_KEY_SALT: Optional[str] = None
RATE_LIMIT_SHADOW: bool = False          # compute + log decisions, enforce nothing
TRUSTED_PROXY_CIDRS: str = "[]"
TRUST_CLOUDFLARE_CONNECTING_IP: bool = False

def get_trusted_proxy_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    values = json.loads(self.TRUSTED_PROXY_CIDRS)
    return tuple(ipaddress.ip_network(value, strict=False) for value in values)
```

Changing `REDIS_URL` to `None` makes "enabled rate limiting without Redis" a rejectable state. Every place that already reads `settings.REDIS_URL` (Celery config, `database`/health) must tolerate `None` or fall back explicitly — grep and fix. Docker Compose and both env examples set `REDIS_URL` explicitly.

Production validation (`validate_runtime_config`) rejects: `RATE_LIMIT_ENABLED` with `REDIS_URL` unset; `REDIS_URL` set but unreachable on a bounded startup ping; missing/short/placeholder salt; invalid or universal `TRUSTED_PROXY_CIDRS`; `TRUST_CLOUDFLARE_CONNECTING_IP` without a trusted CIDR; non-positive limits/windows. Validate without including the salt or Redis URL in error messages.

- [ ] **Step 4: Update environment examples**

Development disables rate limiting explicitly unless Redis is configured. Production contains enabled rate limiting plus non-working placeholders that validation rejects until replaced.

- [ ] **Step 5: Run config/security tests**

Run: `.venv/bin/python -m pytest tests/test_rate_limit_config.py tests/test_environment_examples.py tests/test_spec08_admin_security.py -v`

Expected: PASS; existing production security validation remains fail closed.

- [ ] **Step 6: Commit rate-limit configuration**

```bash
git add config.py .env.example .env.production.example tests/test_rate_limit_config.py tests/test_environment_examples.py
git commit -m "feat: validate trusted proxy and limiter configuration"
```

---

### Task 2: Implement trusted client identity resolution

**Files:**
- Create: `services/client_identity_service.py`
- Create: `tests/test_client_identity_service.py`
- Test: `tests/test_client_identity_service.py`

**Interfaces:**
- Consumes: Starlette `Request`, parsed trusted proxy networks, Cloudflare trust flag.
- Produces: `ClientIdentity`, `resolve_client_identity(request: Request, trusted_networks: tuple[IPv4Network | IPv6Network, ...], trust_cloudflare: bool) -> ClientIdentity`, `digest_client_identity(ip: str, salt: str) -> str`.

- [ ] **Step 1: Write failing direct/spoof/proxy tests**

```python
def test_untrusted_peer_ignores_forwarding_headers():
    request = make_request(
        peer="203.0.113.10",
        headers={"x-forwarded-for": "198.51.100.2", "cf-connecting-ip": "198.51.100.3"},
    )
    identity = resolve_client_identity(request, trusted_networks=())
    assert identity.normalized_ip == "203.0.113.10"
    assert identity.source == "peer"

def test_trusted_proxy_uses_valid_cloudflare_header_when_enabled():
    request = make_request(peer="10.0.0.2", headers={"cf-connecting-ip": "2001:db8::1"})
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=True,
    )
    assert identity.normalized_ip == "2001:db8::1"
```

Add invalid/multiple header, IPv4-mapped IPv6 normalization, and digest-not-containing-IP cases. For trusted XFF, assert the **right-most non-proxy** element wins: `make_request(peer="10.0.0.2", headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9, 10.0.0.2"}, trusted_networks=(ip_network("10.0.0.0/8"),))` resolves to `203.0.113.9`, and rotating the left-most value does not change the subject.

- [ ] **Step 2: Run tests and verify the resolver is absent**

Run: `.venv/bin/python -m pytest tests/test_client_identity_service.py -v`

Expected: FAIL importing the new service.

- [ ] **Step 3: Implement immutable identity resolution**

```python
@dataclass(frozen=True)
class ClientIdentity:
    normalized_ip: str
    source: Literal["peer", "cf-connecting-ip", "x-forwarded-for"]
```

Parse with `ipaddress.ip_address()`. Convert IPv4-mapped IPv6 addresses to their IPv4 form. Treat commas in `CF-Connecting-IP` as invalid.

For `X-Forwarded-For`, only when the immediate peer is trusted: split on commas, parse+normalize each element, then walk **from the right** and take the first address that is not itself in `trusted_networks`. Trusted proxies append the real client and pass through whatever the client sent, so the left-most element is attacker-controlled (spec §4.2). If every element is a trusted-proxy address or nothing parses, fall through to the peer and emit `client_identity_peer_fallback`.

- [ ] **Step 4: Implement HMAC subject digest**

```python
def digest_client_identity(normalized_ip: str, salt: str) -> str:
    return hmac.new(
        salt.encode("utf-8"), normalized_ip.encode("ascii"), hashlib.sha256
    ).hexdigest()
```

The service returns full digest only to the limiter. Logging helpers may expose at most the first 12 hex characters.

- [ ] **Step 5: Run identity tests**

Run: `.venv/bin/python -m pytest tests/test_client_identity_service.py -v`

Expected: PASS; rotating spoofed headers on an untrusted peer produces the same digest.

- [ ] **Step 6: Commit identity resolution**

```bash
git add services/client_identity_service.py tests/test_client_identity_service.py
git commit -m "feat: resolve client identity through trusted proxies"
```

---

### Task 3: Implement the atomic Redis sliding-window service

**Files:**
- Create: `services/rate_limit_service.py`
- Create: `tests/test_rate_limit_service.py`
- Create: `tests/test_rate_limit_redis_integration.py`
- Test: `tests/test_rate_limit_service.py`
- Test: `tests/test_rate_limit_redis_integration.py`

**Interfaces:**
- Consumes: Redis client from `settings.REDIS_URL`, HMAC subject digest from Task 2.
- Produces: `RateLimitDecision`, `RateLimitUnavailableError`, `RedisRateLimiter.check()`, `.peek()`, `.record()`, and `.clear()`.

- [ ] **Step 1: Write failing decision and error-mapping tests**

```python
def test_key_never_contains_raw_ip(fake_redis):
    limiter = RedisRateLimiter(fake_redis, key_prefix="skillpulse:ratelimit:v1")
    limiter.check("public_match", digest("203.0.113.8"), limit=2, window_seconds=60)
    assert all("203.0.113.8" not in key for key in fake_redis.keys("*"))

def test_redis_error_fails_closed():
    limiter = RedisRateLimiter(BrokenRedis())
    with pytest.raises(RateLimitUnavailableError):
        limiter.check("public_match", "abc", 20, 60)
```

- [ ] **Step 2: Write a real-Redis concurrency test before implementation**

Launch 40 concurrent checks from two limiter instances against a limit of 20. Assert exactly 20 decisions are allowed and 20 denied. Mark the test `@pytest.mark.redis_integration` and source its Redis URL from `TEST_REDIS_URL`.

- [ ] **Step 3: Run tests and verify the service is absent**

Run: `.venv/bin/python -m pytest tests/test_rate_limit_service.py -v`

Expected: FAIL importing the new service.

- [ ] **Step 4: Define result and exception types**

```python
@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_after_seconds: int

class RateLimitUnavailableError(RuntimeError):
    pass
```

- [ ] **Step 5: Implement one Lua decision script**

The script receives key, current milliseconds, window milliseconds, limit, unique member, and TTL milliseconds. It executes `ZREMRANGEBYSCORE`, `ZCARD`, conditional `ZADD`, `PEXPIRE`, and oldest-score lookup in one script call. It returns integer fields only.

Use a member formatted as `"{now_ms}:{secrets.token_hex(8)}"`. Set TTL to `window_ms + 60000`. Compute retry/reset values with ceiling division and clamp them to at least one second for denied requests.

Pass a final integer `record` argument into the same script. `peek()` calls it with `0`, so it prunes/counts without adding. `record()` calls it with `1`, so an allowed request is added atomically. `check()` delegates to `record()` for public endpoints, where every allowed attempt consumes the allowance.

- [ ] **Step 6: Implement scoped keys and clearing**

```python
def _key(self, scope: str, subject_digest: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", scope):
        raise ValueError("invalid rate-limit scope")
    return f"{self.key_prefix}:{scope}:{subject_digest}"
```

`clear(scope, digest)` deletes exactly one key and is used only after successful login.

- [ ] **Step 7: Run unit and real-Redis tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rate_limit_service.py -v
TEST_REDIS_URL=redis://127.0.0.1:6379/15 .venv/bin/python -m pytest tests/test_rate_limit_redis_integration.py -v
```

Expected: PASS; the concurrency test allows exactly the configured limit.

- [ ] **Step 8: Commit the shared limiter**

```bash
git add services/rate_limit_service.py tests/test_rate_limit_service.py tests/test_rate_limit_redis_integration.py
git commit -m "feat: add atomic Redis sliding-window limiter"
```

---

### Task 4: Replace public in-process middleware enforcement

**Files:**
- Modify: `app.py:142-195`
- Create: `services/rate_limit_policy.py`
- Create: `tests/test_public_rate_limit_middleware.py`
- Modify: `tests/test_api_smoke_and_contracts.py`
- Test: `tests/test_public_rate_limit_middleware.py`

**Interfaces:**
- Consumes: identity service from Task 2, `RedisRateLimiter` from Task 3, existing per-scope settings.
- Produces: `resolve_rate_limit_policy(method: str, path: str) -> RateLimitPolicy | None` and shared public middleware.

- [ ] **Step 1: Write failing public middleware tests**

```python
@pytest.mark.parametrize(
    "path,scope,limit",
    [
        ("/api/v1/jobs/search/hybrid", "public_search", 60),
        ("/api/v1/match", "public_match", 20),
        ("/api/v1/match/explain", "ai_explain", 5),
        ("/api/v1/extract", "ai_extract", 10),
    ],
)
def test_policy_maps_normalized_route_groups(path, scope, limit):
    policy = resolve_rate_limit_policy("POST", path)
    assert (policy.scope, policy.limit, policy.window_seconds) == (scope, limit, 60)
```

Add tests for trailing slash normalization, unmetered GETs, `429` headers/body, spoofed XFF, and Redis failure = `503`.

- [ ] **Step 2: Run middleware tests and verify old process-local behavior fails**

Run: `.venv/bin/python -m pytest tests/test_public_rate_limit_middleware.py -v`

Expected: FAIL because no shared policy/service is wired.

- [ ] **Step 3: Implement exact route-group policy**

```python
@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    limit: int
    window_seconds: int
```

Match normalized method/path against an ordered table so `/api/v1/match/explain` is checked before `/api/v1/match`. Return no policy for health probes, GET requests, and unlisted routes. Scopes `ai_explain` / `ai_extract` map operator-authenticated routes and are enforced anyway (spec §5): the middleware runs before route auth, so an unauthenticated caller still consumes that identity's `ai_*` allowance before being `401`'d — that is intentional and covered by a test.

- [ ] **Step 4: Replace `_RATE_LIMIT_STORE` middleware logic**

Delete `_RATE_LIMIT_STORE`, `defaultdict`, timestamp filtering, and direct proxy-header reads. Resolve identity through Task 2, HMAC it, call the limiter once, and attach `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset` to allowed responses.

Return JSON `429` with `Retry-After`, `Cache-Control: no-store`, and request ID when denied. Map `RateLimitUnavailableError` to JSON `503` without calling the protected endpoint.

When `settings.RATE_LIMIT_SHADOW` is true: still resolve identity and call the limiter, still emit the §9 events (tagged `shadow=true`), but never return `429`/`503` — let the request through. This is the rollout observe-only state (spec §11). Add a test that a would-be-denied request returns its normal 2xx under shadow mode while logging the rejection decision.

- [ ] **Step 5: Run public middleware/API tests**

Run: `.venv/bin/python -m pytest tests/test_public_rate_limit_middleware.py tests/test_api_smoke_and_contracts.py tests/test_hybrid_search_and_matcher.py -v`

Expected: PASS; direct spoofed headers cannot create new allowances.

- [ ] **Step 6: Commit public enforcement**

```bash
git add app.py services/rate_limit_policy.py tests/test_public_rate_limit_middleware.py tests/test_api_smoke_and_contracts.py
git commit -m "fix: enforce public limits through shared Redis"
```

---

### Task 5: Replace operator login failure counters

**Files:**
- Modify: `api/v1/auth.py:109-136,270-332`
- Modify: `tests/test_spec08_admin_security.py`
- Create: `tests/test_operator_login_rate_limit.py`
- Test: `tests/test_operator_login_rate_limit.py`

**Interfaces:**
- Consumes: identity service, `RedisRateLimiter.peek()`, `.record()`, and `.clear()`.
- Produces: distributed `operator_login_failure` enforcement with five failures per 900 seconds.

- [ ] **Step 1: Write failing shared-login-limit tests**

```python
def test_failed_logins_share_limit_across_app_instances(app_factory):
    first = app_factory(shared_redis=True)
    second = app_factory(shared_redis=True)
    for _ in range(3):
        assert first.post(LOGIN, json={"key": "wrong"}).status_code == 401
    for _ in range(2):
        assert second.post(LOGIN, json={"key": "wrong"}).status_code == 401
    assert first.post(LOGIN, json={"key": "correct"}).status_code == 429
```

Add successful-login clearing, unrelated subject isolation, spoofed-header resistance, and Redis failure = `503`.

- [ ] **Step 2: Run tests and verify process-local counters fail distribution**

Run: `.venv/bin/python -m pytest tests/test_operator_login_rate_limit.py -v`

Expected: FAIL because `_FAILED_LOGINS` is local to one process.

- [ ] **Step 3: Replace login helper functions**

Delete `_FAILED_LOGINS`, `_check_login_rate_limit`, `_record_login_failure`, and `_record_login_success`. Resolve/digest identity at the start of `admin_login`.

`tests/test_spec08_admin_security.py` imports `_FAILED_LOGINS` at module scope (`from api.v1.auth import … _FAILED_LOGINS`) and calls `.clear()` in fixtures — that import breaks collection of the whole file the moment the symbol is gone. In the same commit: remove that import, replace the fixture teardown with a Redis-key flush against the test limiter, and update `test_login_rate_limiting`'s assertion on the old message string (`"Too many failed login attempts"`) to the new `429` body (`"Rate limit exceeded. Please try again later."`).

Call `peek("operator_login_failure", digest, 5, 900)` before credential comparison. To count only failures, use the operations defined in Task 3:

```python
peek(scope, digest, limit, window_seconds) -> RateLimitDecision
record(scope, digest, limit, window_seconds) -> RateLimitDecision
```

Both operations are Lua-backed; `peek` prunes/counts without adding, while `record` prunes/counts/adds atomically. A blocked `peek` returns `429`; an invalid credential calls `record`; a successful credential calls `clear`.

- [ ] **Step 4: Preserve constant-time auth and audit behavior**

Continue using `secrets.compare_digest`. Audit only result category and short subject digest. Never record the supplied key or raw identity.

- [ ] **Step 5: Run operator security tests**

Run: `.venv/bin/python -m pytest tests/test_operator_login_rate_limit.py tests/test_spec08_admin_security.py -v`

Expected: PASS; session/cookie/origin protections are unchanged.

- [ ] **Step 6: Commit distributed login enforcement**

```bash
git add api/v1/auth.py services/rate_limit_service.py tests/test_operator_login_rate_limit.py tests/test_spec08_admin_security.py
git commit -m "fix: distribute operator login failure limits"
```

---

### Task 6: Integrate Redis into readiness and deployment

**Files:**
- Modify: `services/readiness_service.py`
- Modify: `app.py`
- Modify: `docker-compose.yml`
- Create: `tests/test_rate_limit_readiness.py`
- Modify: `tests/test_runtime_startup_and_health.py`
- Test: `tests/test_rate_limit_readiness.py`

**Interfaces:**
- Consumes: runtime readiness service and rate-limit settings.
- Produces: `check_redis_readiness() -> DependencyReadiness`, Redis-aware `/health/ready` that does **not** gate traffic admission on Redis (spec §7).

- [ ] **Step 1: Write failing Redis readiness tests (Redis does not gate admission)**

```python
def test_redis_outage_keeps_readiness_200_but_reports_degraded(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(readiness, "check_redis_readiness", lambda: degraded_dependency("redis"))
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["dependencies"]["database"] == "connected"
    assert response.json()["dependencies"]["redis"] == "degraded"

def test_database_outage_still_makes_readiness_503(monkeypatch):
    monkeypatch.setattr(app, "check_database_readiness", lambda: unavailable_result())
    assert client.get("/health/ready").status_code == 503

def test_liveness_ignores_redis(monkeypatch):
    monkeypatch.setattr(readiness, "check_redis_readiness", Mock(side_effect=AssertionError))
    assert client.get("/health/live").status_code == 200
```

- [ ] **Step 2: Run tests and verify readiness has no Redis state yet**

Run: `.venv/bin/python -m pytest tests/test_rate_limit_readiness.py -v`

Expected: FAIL because readiness has no Redis dependency reporting.

- [ ] **Step 3: Add bounded Redis readiness as a non-gating detail**

Ping Redis with a one-second socket/connect timeout only when rate limiting is enabled. Add its state to the readiness response as `dependencies.redis` = `"connected"` / `"degraded"` (never URLs). **Only the database result decides the 200/503 status code** — a Redis outage leaves readiness `200` so unmetered reads and liveness stay reachable (spec §7). The per-request fail-closed `503` from Task 4 / Task 5 is what protects quota during a Redis outage.

- [ ] **Step 4: Configure deployment health dependencies**

Keep the API service `depends_on` PostgreSQL healthy (blocking) and Redis healthy (start ordering only — a later Redis failure must not cascade to the API container via readiness). Add Redis health-check authentication configuration if production Redis requires it; do not embed a password in the Compose file.

- [ ] **Step 5: Run readiness and Compose tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rate_limit_readiness.py tests/test_runtime_startup_and_health.py -v
docker compose config --quiet
```

Expected: PASS; Redis loss is reported in `dependencies.redis` but does not change the readiness status code or affect liveness.

- [ ] **Step 6: Commit readiness integration**

```bash
git add services/readiness_service.py app.py docker-compose.yml tests/test_rate_limit_readiness.py tests/test_runtime_startup_and_health.py
git commit -m "feat: include limiter Redis in readiness"
```

---

### Task 7: Add observability, documentation, and full verification

**Files:**
- Modify: `services/rate_limit_service.py`
- Modify: `services/client_identity_service.py`
- Modify: `README.md`
- Create: `docs/operations/rate-limit-alerts.md`
- Create: `tests/test_rate_limit_observability.py`
- Test: `tests/test_rate_limit_observability.py`

**Interfaces:**
- Consumes: shared rate-limit decisions and client identities.
- Produces: structured allowed/rejected/error/proxy metrics and deployment documentation.

- [ ] **Step 1: Write failing log-redaction tests**

```python
def test_limiter_logs_never_contain_raw_identity(caplog):
    raw_ip = "203.0.113.44"
    exercise_allowed_and_denied_requests(raw_ip)
    assert raw_ip not in caplog.text
    assert "x-forwarded-for" not in caplog.text.lower()

def test_redis_error_log_uses_stable_category(caplog):
    exercise_redis_failure()
    assert "rate_limit_store_unavailable" in caplog.text
```

- [ ] **Step 2: Implement structured event hooks**

Emit stable events `rate_limit_allowed`, `rate_limit_rejected`, `rate_limit_store_unavailable`, `proxy_header_rejected`, and `client_identity_peer_fallback`. Include scope, decision latency, request ID, and at most the 12-character digest prefix.

- [ ] **Step 3: Update README operations guidance**

Document Redis requirement, trusted CIDR configuration, direct-origin behavior, failure policy, response headers, integration-test command, and safe proxy rollout. Do not recommend universal CIDRs.

Create `docs/operations/rate-limit-alerts.md` with deploy-platform-neutral alert definitions: Redis errors sustained for more than one minute; limiter-generated `503` responses above 1% of protected requests over five minutes; and per-scope `429` volume above five times the seven-day baseline. State the required event field names and exclude raw identities from example queries.

- [ ] **Step 4: Run the complete verification suite**

Run:

```bash
.venv/bin/python -m pytest -q
TEST_REDIS_URL=redis://127.0.0.1:6379/15 .venv/bin/python -m pytest tests/test_rate_limit_redis_integration.py -v
for f in tests/*.test.js; do node --test "$f"; done
docker compose config --quiet
git diff --check
```

Expected: all unit, integration, browser, and configuration checks pass; no `_RATE_LIMIT_STORE` or `_FAILED_LOGINS` symbol remains.

- [ ] **Step 5: Commit observability and documentation**

```bash
git add services/rate_limit_service.py services/client_identity_service.py README.md docs/operations/rate-limit-alerts.md tests/test_rate_limit_observability.py
git commit -m "docs: document distributed rate-limit operations"
```
