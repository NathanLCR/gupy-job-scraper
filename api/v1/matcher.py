"""
SkillPulse AI Candidate Matcher API router alias.
"""

from api.v1.match import (
    create_candidate_profile,
    get_candidate_profile,
    match_candidate_cv,
    router,
)

__all__ = [
    "create_candidate_profile",
    "get_candidate_profile",
    "match_candidate_cv",
    "router",
]
