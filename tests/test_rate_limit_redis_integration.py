import concurrent.futures
import os
import secrets
import pytest
import redis

from services.client_identity_service import digest_client_identity
from services.rate_limit_service import RedisRateLimiter

TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
SALT = "secure-random-salt-for-testing-must-be-32-chars"


@pytest.fixture(scope="module")
def redis_client():
    """Connect to test Redis instance; skip integration suite if unreachable."""
    try:
        client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=False)
        client.ping()
    except Exception as exc:
        pytest.skip(f"Real Redis integration test skipped: cannot connect to {TEST_REDIS_URL} ({exc})")
    
    yield client
    client.close()


@pytest.fixture(autouse=True)
def cleanup_redis_keys(redis_client):
    """Flush keys created in test DB before and after each test."""
    try:
        keys = redis_client.keys("skillpulse:ratelimit:test:*")
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass
    yield
    try:
        keys = redis_client.keys("skillpulse:ratelimit:test:*")
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass


@pytest.mark.redis_integration
def test_concurrent_sliding_window_atomicity_allows_exact_limit(redis_client):
    """
    Launch 40 concurrent checks from two independent limiter instances
    against a configured limit of 20. Assert exactly 20 are allowed and 20 are denied.
    """
    limiter_1 = RedisRateLimiter(redis_client, key_prefix="skillpulse:ratelimit:test")
    limiter_2 = RedisRateLimiter(redis_client, key_prefix="skillpulse:ratelimit:test")

    subject = digest_client_identity(f"203.0.113.{secrets.randbelow(250)}", SALT)
    limit = 20
    window_seconds = 60

    def run_check(worker_id: int):
        limiter = limiter_1 if worker_id % 2 == 0 else limiter_2
        return limiter.check("public_match", subject, limit=limit, window_seconds=window_seconds)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(run_check, i) for i in range(40)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    allowed_count = sum(1 for r in results if r.allowed is True)
    denied_count = sum(1 for r in results if r.allowed is False)

    assert allowed_count == 20
    assert denied_count == 20


@pytest.mark.redis_integration
def test_real_redis_key_ttl_and_expiry(redis_client):
    """Verify that key TTL is set to window_ms + 60s in real Redis."""
    limiter = RedisRateLimiter(redis_client, key_prefix="skillpulse:ratelimit:test")
    subject = digest_client_identity("198.51.100.77", SALT)

    limiter.record("public_search", subject, limit=5, window_seconds=30)
    key = f"skillpulse:ratelimit:test:public_search:{subject}"

    pttl = redis_client.pttl(key)
    # Expected TTL around 30s + 60s = 90,000 ms
    assert 80000 <= pttl <= 91000


@pytest.mark.redis_integration
def test_real_redis_clear_deletes_key(redis_client):
    """Verify that clear() removes key from real Redis."""
    limiter = RedisRateLimiter(redis_client, key_prefix="skillpulse:ratelimit:test")
    subject = digest_client_identity("198.51.100.88", SALT)

    limiter.record("operator_login_failure", subject, limit=1, window_seconds=900)
    key = f"skillpulse:ratelimit:test:operator_login_failure:{subject}"
    assert redis_client.exists(key) == 1

    limiter.clear("operator_login_failure", subject)
    assert redis_client.exists(key) == 0
