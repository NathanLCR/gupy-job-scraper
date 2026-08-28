from dataclasses import dataclass
from typing import Optional
from config import settings


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    limit: int
    window_seconds: int


def resolve_rate_limit_policy(method: str, path: str) -> Optional[RateLimitPolicy]:
    """
    Map HTTP method and path to the rate limit policy for route groups.
    Only specified POST endpoints are metered; GETs, health probes, and unlisted
    routes return None.
    """
    if method != "POST":
        return None

    clean_path = path.rstrip("/") if len(path) > 1 else path
    prefix = settings.API_V1_PREFIX.rstrip("/")

    # Ordered matching: match/explain must precede match
    if clean_path == f"{prefix}/match/explain":
        return RateLimitPolicy(
            scope="ai_explain",
            limit=settings.RATE_LIMIT_EXPLAIN_RPM,
            window_seconds=60,
        )

    if clean_path == f"{prefix}/match":
        return RateLimitPolicy(
            scope="public_match",
            limit=settings.RATE_LIMIT_MATCH_RPM,
            window_seconds=60,
        )

    if clean_path == f"{prefix}/extract":
        return RateLimitPolicy(
            scope="ai_extract",
            limit=settings.RATE_LIMIT_EXTRACT_RPM,
            window_seconds=60,
        )

    if clean_path == f"{prefix}/jobs/search" or clean_path.startswith(f"{prefix}/jobs/search/"):
        return RateLimitPolicy(
            scope="public_search",
            limit=settings.RATE_LIMIT_SEARCH_RPM,
            window_seconds=60,
        )

    return None
