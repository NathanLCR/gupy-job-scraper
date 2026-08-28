import math
import pytest
import redis.exceptions

from services.client_identity_service import digest_client_identity
from services.rate_limit_service import (
    RedisRateLimiter,
    RateLimitDecision,
    RateLimitUnavailableError,
)

SALT = "secure-random-salt-for-testing-must-be-32-chars"


class FakeRedis:
    """In-memory Redis fake implementing the Lua script and key operations for unit tests."""

    def __init__(self):
        self.store: dict[str, list[tuple[int, str]]] = {}
        self.ttls: dict[str, int] = {}

    def keys(self, pattern: str = "*") -> list[str]:
        return list(self.store.keys())

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.ttls.pop(k, None)
                count += 1
        return count

    def eval(self, script: str, numkeys: int, key: str, *args) -> list[int]:
        now_ms = int(args[0])
        window_ms = int(args[1])
        limit = int(args[2])
        member = str(args[3])
        ttl_ms = int(args[4])
        record = int(args[5])

        entries = self.store.setdefault(key, [])
        clear_before = now_ms - window_ms
        # Prune entries strictly older than window
        entries = [e for e in entries if e[0] > clear_before]
        self.store[key] = entries

        current_count = len(entries)
        allowed = 0

        if current_count < limit:
            allowed = 1
            if record == 1:
                entries.append((now_ms, member))
                current_count += 1
        else:
            allowed = 0

        self.ttls[key] = ttl_ms

        oldest_ms = entries[0][0] if entries else 0
        return [allowed, current_count, oldest_ms]


class BrokenRedis:
    """Broken Redis client that always raises network / connection errors."""

    def eval(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("Could not connect to Redis server")

    def delete(self, *args, **kwargs):
        raise redis.exceptions.TimeoutError("Redis command timed out")

    def ping(self):
        raise redis.exceptions.ConnectionError("Could not connect to Redis server")


@pytest.fixture
def fake_redis():
    return FakeRedis()


def test_key_never_contains_raw_ip(fake_redis):
    raw_ip = "203.0.113.8"
    subject = digest_client_identity(raw_ip, SALT)
    limiter = RedisRateLimiter(fake_redis, key_prefix="skillpulse:ratelimit:v1")
    limiter.check("public_match", subject, limit=2, window_seconds=60)

    keys = fake_redis.keys("*")
    assert len(keys) == 1
    assert raw_ip not in keys[0]
    assert keys[0] == f"skillpulse:ratelimit:v1:public_match:{subject}"


def test_redis_error_fails_closed():
    limiter = RedisRateLimiter(BrokenRedis())
    with pytest.raises(RateLimitUnavailableError):
        limiter.check("public_match", "abc", 20, 60)

    with pytest.raises(RateLimitUnavailableError):
        limiter.peek("public_match", "abc", 20, 60)

    with pytest.raises(RateLimitUnavailableError):
        limiter.clear("public_match", "abc")


@pytest.mark.parametrize("invalid_scope", ["public-match", "public/match", "scope!", "SCOPE", " "])
def test_invalid_scope_raises_value_error(fake_redis, invalid_scope):
    limiter = RedisRateLimiter(fake_redis)
    with pytest.raises(ValueError, match="invalid rate-limit scope"):
        limiter.check(invalid_scope, "abc", 10, 60)


def test_check_enforces_limit_sliding_window(fake_redis):
    limiter = RedisRateLimiter(fake_redis)
    subject = digest_client_identity("198.51.100.22", SALT)

    # Allow 3 requests per 60s
    d1 = limiter.check("public_search", subject, limit=3, window_seconds=60)
    assert d1.allowed is True
    assert d1.limit == 3
    assert d1.remaining == 2
    assert d1.retry_after_seconds == 0

    d2 = limiter.check("public_search", subject, limit=3, window_seconds=60)
    assert d2.allowed is True
    assert d2.remaining == 1
    assert d2.retry_after_seconds == 0

    d3 = limiter.check("public_search", subject, limit=3, window_seconds=60)
    assert d3.allowed is True
    assert d3.remaining == 0
    assert d3.retry_after_seconds == 0

    # 4th request must be rejected
    d4 = limiter.check("public_search", subject, limit=3, window_seconds=60)
    assert d4.allowed is False
    assert d4.remaining == 0
    assert d4.retry_after_seconds >= 1
    assert d4.reset_after_seconds >= 1


def test_peek_does_not_consume_allowance(fake_redis):
    limiter = RedisRateLimiter(fake_redis)
    subject = digest_client_identity("198.51.100.25", SALT)

    # 3 peeks with limit 2
    p1 = limiter.peek("operator_login_failure", subject, limit=2, window_seconds=900)
    p2 = limiter.peek("operator_login_failure", subject, limit=2, window_seconds=900)
    p3 = limiter.peek("operator_login_failure", subject, limit=2, window_seconds=900)

    assert p1.allowed is True and p1.remaining == 2
    assert p2.allowed is True and p2.remaining == 2
    assert p3.allowed is True and p3.remaining == 2

    # Now record 1 failure
    r1 = limiter.record("operator_login_failure", subject, limit=2, window_seconds=900)
    assert r1.allowed is True and r1.remaining == 1

    # Next peek shows 1 remaining
    p4 = limiter.peek("operator_login_failure", subject, limit=2, window_seconds=900)
    assert p4.allowed is True and p4.remaining == 1


def test_clear_resets_allowance_for_subject_and_scope(fake_redis):
    limiter = RedisRateLimiter(fake_redis)
    subject = digest_client_identity("198.51.100.30", SALT)

    limiter.record("operator_login_failure", subject, limit=1, window_seconds=900)
    blocked = limiter.peek("operator_login_failure", subject, limit=1, window_seconds=900)
    assert blocked.allowed is False

    limiter.clear("operator_login_failure", subject)

    unblocked = limiter.peek("operator_login_failure", subject, limit=1, window_seconds=900)
    assert unblocked.allowed is True
    assert unblocked.remaining == 1


def test_distinct_scopes_and_subjects_are_isolated(fake_redis):
    limiter = RedisRateLimiter(fake_redis)
    sub_a = digest_client_identity("198.51.100.41", SALT)
    sub_b = digest_client_identity("198.51.100.42", SALT)

    # sub_a uses all allowance for public_match
    limiter.check("public_match", sub_a, limit=1, window_seconds=60)
    assert limiter.check("public_match", sub_a, limit=1, window_seconds=60).allowed is False

    # sub_b is unaffected
    assert limiter.check("public_match", sub_b, limit=1, window_seconds=60).allowed is True

    # sub_a on public_search is unaffected
    assert limiter.check("public_search", sub_a, limit=1, window_seconds=60).allowed is True
