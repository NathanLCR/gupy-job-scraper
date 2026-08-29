import logging

import pytest

from services.rate_limit_service import RateLimitUnavailableError, RedisRateLimiter


class SecretFailingRedis:
    def eval(self, *args, **kwargs):
        raise ConnectionError(
            "redis://operator:redis-password@private-redis.internal:6379/0"
        )


def test_rate_limit_store_failure_log_omits_connection_details(caplog):
    limiter = RedisRateLimiter(SecretFailingRedis())

    with caplog.at_level(logging.ERROR), pytest.raises(RateLimitUnavailableError):
        limiter.check("public_match", "a" * 64, 20, 60)

    assert "rate_limit_store_unavailable" in caplog.text
    assert "redis-password" not in caplog.text
    assert "private-redis.internal" not in caplog.text
    assert "Traceback" not in caplog.text
