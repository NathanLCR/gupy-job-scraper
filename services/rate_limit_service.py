import logging
import math
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

import redis
import redis.exceptions
from config import settings

logger = logging.getLogger("skillpulse.rate_limit")

LUA_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl_ms = tonumber(ARGV[5])
local record = tonumber(ARGV[6])

local clear_before = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

local current_count = redis.call('ZCARD', key)
local allowed = 0

if current_count < limit then
    allowed = 1
    if record == 1 then
        redis.call('ZADD', key, now_ms, member)
        current_count = current_count + 1
    end
else
    allowed = 0
end

redis.call('PEXPIRE', key, ttl_ms)

local oldest_ms = 0
if current_count > 0 then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if oldest and #oldest >= 2 then
        oldest_ms = tonumber(oldest[2])
    end
end

return {allowed, current_count, oldest_ms}
"""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_after_seconds: int


class RateLimitUnavailableError(RuntimeError):
    """Raised when Redis limiter cannot enforce decisions due to network or store failure."""
    pass


class RedisRateLimiter:
    """
    Atomic Redis sorted-set sliding window rate limiter.
    All operations are evaluated atomically inside a single Lua script.
    """

    def __init__(self, redis_client: Any, key_prefix: str = "skillpulse:ratelimit:v1"):
        self.redis = redis_client
        self.key_prefix = key_prefix

    def _key(self, scope: str, subject_digest: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", scope):
            raise ValueError(f"invalid rate-limit scope: {scope}")
        return f"{self.key_prefix}:{scope}:{subject_digest}"

    def _eval(
        self,
        scope: str,
        subject_digest: str,
        limit: int,
        window_seconds: int,
        record: int,
    ) -> RateLimitDecision:
        key = self._key(scope, subject_digest)
        now_ms = int(time.time() * 1000)
        window_ms = int(window_seconds * 1000)
        ttl_ms = window_ms + 60000
        member = f"{now_ms}:{secrets.token_hex(8)}"

        try:
            res = self.redis.eval(
                LUA_SLIDING_WINDOW_SCRIPT,
                1,
                key,
                str(now_ms),
                str(window_ms),
                str(limit),
                member,
                str(ttl_ms),
                str(record),
            )
        except Exception as exc:
            logger.error(
                "Rate limit store unavailable during evaluation",
                exc_info=True,
                extra={"failure_category": "rate_limit_store_unavailable", "scope": scope},
            )
            raise RateLimitUnavailableError(f"Rate limit store unavailable: {exc}") from exc

        allowed_int = int(res[0])
        current_count = int(res[1])
        oldest_ms = int(res[2])

        allowed = bool(allowed_int == 1)
        remaining = max(0, limit - current_count)

        if oldest_ms > 0:
            diff_ms = max(0, (oldest_ms + window_ms) - now_ms)
            reset_after_seconds = max(1, math.ceil(diff_ms / 1000)) if current_count > 0 else 0
        else:
            reset_after_seconds = window_seconds if current_count > 0 else 0

        if not allowed:
            retry_after_seconds = max(1, reset_after_seconds)
        else:
            retry_after_seconds = 0

        return RateLimitDecision(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            retry_after_seconds=retry_after_seconds,
            reset_after_seconds=reset_after_seconds,
        )

    def check(
        self, scope: str, subject_digest: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """Check and atomically record an attempt in the sliding window."""
        return self._eval(scope, subject_digest, limit, window_seconds, record=1)

    def record(
        self, scope: str, subject_digest: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """Record an attempt in the sliding window."""
        return self._eval(scope, subject_digest, limit, window_seconds, record=1)

    def peek(
        self, scope: str, subject_digest: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """Check allowance without recording an attempt."""
        return self._eval(scope, subject_digest, limit, window_seconds, record=0)

    def clear(self, scope: str, subject_digest: str) -> None:
        """Delete rate-limit sorted set for a specific scope and subject."""
        key = self._key(scope, subject_digest)
        try:
            self.redis.delete(key)
        except Exception as exc:
            logger.error(
                "Rate limit store unavailable during clear",
                exc_info=True,
                extra={"failure_category": "rate_limit_store_unavailable", "scope": scope},
            )
            raise RateLimitUnavailableError(f"Rate limit store unavailable: {exc}") from exc


_RATE_LIMITER: Optional[RedisRateLimiter] = None


def get_rate_limiter(redis_url: Optional[str] = None) -> RedisRateLimiter:
    """Get or create singleton RedisRateLimiter instance."""
    global _RATE_LIMITER
    if _RATE_LIMITER is not None:
        return _RATE_LIMITER

    url = redis_url or getattr(settings, "REDIS_URL", None)
    if not url:
        raise RateLimitUnavailableError("Redis URL is not configured")

    client = redis.Redis.from_url(url, decode_responses=False)
    _RATE_LIMITER = RedisRateLimiter(client)
    return _RATE_LIMITER
