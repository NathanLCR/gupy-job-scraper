"""
SkillPulse AI Hybrid Search Service.
Combines Dense Semantic Vector Search (pgvector) and Sparse Full-Text Search
using Reciprocal Rank Fusion (RRF, k=60) with faceted filtering (SPEC §3.4).
"""

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from database import SessionLocal
from entities import City, Company, HardSkill, Job, State
from services.embedding_service import (
    cosine_similarity,
    embed_job,
    get_embedding,
)

logger = logging.getLogger(__name__)

RRF_K = 60  # Standard RRF constant parameter (SPEC §3.4)


@dataclass
class HybridSearchResultItem:
    job_id: int
    job: Optional[Job] = None
    job_dict: Optional[Dict[str, Any]] = None
    rrf_score: float = 0.0
    dense_score: float = 0.0
    sparse_score: float = 0.0
    dense_rank: int = 0
    sparse_rank: int = 0
    normalized_score: float = 0.0


def compute_rrf_score(
    dense_rank: Optional[int],
    sparse_rank: Optional[int],
    k: int = RRF_K,
    dense_weight: float = 0.5,
    sparse_weight: float = 0.5,
) -> float:
    """
    Compute Reciprocal Rank Fusion score for a document.
    RRF(d) = sum( w_m / (k + r_m(d)) )
    """
    score = 0.0
    if dense_rank is not None and dense_rank > 0:
        score += dense_weight / (k + dense_rank)
    if sparse_rank is not None and sparse_rank > 0:
        score += sparse_weight / (k + sparse_rank)
    return score


def _compute_sparse_text_score(query_tokens: List[str], job: Job) -> float:
    """
    Compute sparse full-text lexical match score for a job posting.
    Applies field-specific term weighting (Title > Skills > Tech Stack > Description).
    """
    if not query_tokens:
        return 0.0

    title = (job.job_title or "").lower()
    description = (job.description or "").lower()
    company_name = (job.company.name if job.company else "").lower()

    hard_skills = [s.name.lower() for s in (job.hard_skills or [])]
    tech_stack = [s.lower() for s in (job.tech_stack or [])]

    score = 0.0
    for token in query_tokens:
        tok = token.lower()
        if tok in title:
            score += 3.0
        if any(tok == s or tok in s for s in hard_skills):
            score += 2.5
        if any(tok == s or tok in s for s in tech_stack):
            score += 2.0
        if tok in company_name:
            score += 1.5
        if tok in description:
            # Sublinear frequency count for description
            count = description.count(tok)
            score += 1.0 + math.log(max(1, count)) * 0.5

    return score


def hybrid_search_jobs(
    query: str,
    db: Optional[Session] = None,
    region: Optional[str] = None,
    country_code: Optional[str] = None,
    workplace_type: Optional[str] = None,
    seniority: Optional[str] = None,
    min_salary: Optional[int] = None,
    max_salary: Optional[int] = None,
    skill: Optional[str] = None,
    location: Optional[str] = None,
    top_k: int = 20,
    dense_weight: float = 0.5,
    sparse_weight: float = 0.5,
    k: int = RRF_K,
) -> List[HybridSearchResultItem]:
    """
    Perform Reciprocal Rank Fusion (RRF, k=60) Hybrid Search across job postings.
    1. Filters candidate jobs by metadata (region, country, seniority, salary, etc.).
    2. Computes Dense Vector Cosine Similarity against query embedding.
    3. Computes Sparse BM25 / Full-Text Lexical score.
    4. Aggregates ranks using RRF and returns ranked results.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Base query with relational joins
        stmt = select(Job)

        # Faceted filters
        if region and region.lower() != "global":
            stmt = stmt.where(Job.region.ilike(f"%{region.strip()}%"))
        if country_code:
            stmt = stmt.where(Job.country_code.ilike(f"%{country_code.strip()}%"))
        if workplace_type:
            stmt = stmt.where(Job.workplace_type.ilike(f"%{workplace_type.strip()}%"))
        if seniority:
            stmt = stmt.where(Job.seniority.ilike(f"%{seniority.strip()}%"))
        if min_salary is not None:
            stmt = stmt.where(Job.salary >= min_salary)
        if max_salary is not None:
            stmt = stmt.where(Job.salary <= max_salary)

        all_candidates = db.scalars(stmt).all()

        # Additional in-memory filtering for location and skill if needed
        filtered_jobs: List[Job] = []
        for job in all_candidates:
            if location:
                loc_lower = location.lower()
                city_name = (job.city.name if job.city else "").lower()
                state_name = (job.state.name if job.state else "").lower()
                if loc_lower not in city_name and loc_lower not in state_name:
                    continue

            if skill:
                sk_lower = skill.lower()
                hard_skill_names = [s.name.lower() for s in (job.hard_skills or [])]
                tech_stacks = [t.lower() for t in (job.tech_stack or [])]
                if not any(sk_lower in s for s in hard_skill_names) and not any(sk_lower in t for t in tech_stacks):
                    continue

            filtered_jobs.append(job)

        if not filtered_jobs:
            return []

        # 1. Dense Semantic Vector Search
        query_cleaned = (query or "").strip()
        query_embedding = get_embedding(query_cleaned) if query_cleaned else None

        dense_scored: List[Tuple[Job, float]] = []
        for job in filtered_jobs:
            if query_embedding is not None:
                # Use stored embedding or generate dynamically
                job_vec = job.embedding if getattr(job, "embedding", None) is not None else embed_job(job)
                if isinstance(job_vec, list):
                    sim = cosine_similarity(query_embedding, job_vec)
                else:
                    sim = 0.0
            else:
                sim = 0.5
            dense_scored.append((job, sim))

        # Sort descending by dense similarity
        dense_scored.sort(key=lambda x: x[1], reverse=True)
        dense_ranks: Dict[int, int] = {job.id: rank + 1 for rank, (job, _) in enumerate(dense_scored)}
        dense_score_map: Dict[int, float] = {job.id: score for job, score in dense_scored}

        # 2. Sparse Full-Text Search
        query_tokens = [t for t in re.findall(r"\w+", query_cleaned) if len(t) > 1]
        sparse_scored: List[Tuple[Job, float]] = []
        for job in filtered_jobs:
            sparse_score = _compute_sparse_text_score(query_tokens, job)
            sparse_scored.append((job, sparse_score))

        # Sort descending by sparse lexical score
        sparse_scored.sort(key=lambda x: x[1], reverse=True)
        sparse_ranks: Dict[int, int] = {job.id: rank + 1 for rank, (job, _) in enumerate(sparse_scored)}
        sparse_score_map: Dict[int, float] = {job.id: score for job, score in sparse_scored}

        # 3. Reciprocal Rank Fusion (RRF, k=60) Aggregation
        max_possible_rrf = (dense_weight / (k + 1)) + (sparse_weight / (k + 1))
        results: List[HybridSearchResultItem] = []

        for job in filtered_jobs:
            d_rank = dense_ranks.get(job.id, len(filtered_jobs))
            s_rank = sparse_ranks.get(job.id, len(filtered_jobs))
            d_score = dense_score_map.get(job.id, 0.0)
            s_score = sparse_score_map.get(job.id, 0.0)

            rrf = compute_rrf_score(
                dense_rank=d_rank,
                sparse_rank=s_rank,
                k=k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
            )

            norm_score = round((rrf / max(1e-9, max_possible_rrf)) * 100, 1)

            results.append(
                HybridSearchResultItem(
                    job_id=job.id,
                    job=job,
                    job_dict=job.to_dict(),
                    rrf_score=round(rrf, 6),
                    dense_score=round(d_score, 4),
                    sparse_score=round(s_score, 4),
                    dense_rank=d_rank,
                    sparse_rank=s_rank,
                    normalized_score=min(100.0, max(0.0, norm_score)),
                )
            )

        # Sort by RRF score descending
        results.sort(key=lambda x: x.rrf_score, reverse=True)
        return results[:top_k]

    finally:
        if close_db:
            db.close()
