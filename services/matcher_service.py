"""
SkillPulse AI Candidate Matcher & Skill Gap Analysis Service.
Coordinates resume parsing, multi-tier cascade extraction, canonical taxonomy mapping,
composite fit score calculation (0.50*Hard + 0.20*Soft + 0.30*Vector),
and granular gap breakdown with upskilling recommendations (SPEC §3.5).
"""

from collections import Counter
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import SessionLocal
from entities import CandidateProfile, HardSkill, Job, NiceToHaveSkill, SoftSkill
from services.embedding_service import (
    cosine_similarity,
    embed_job,
    embed_resume_text,
)
from services.extractor_service import extract_cascade
from services.taxonomy_service import normalize_skills

logger = logging.getLogger(__name__)


def _extract_skill_set(skills: Optional[List[Any]]) -> Set[str]:
    """Helper to extract clean lowercase skill strings."""
    result = set()
    for s in skills or []:
        if hasattr(s, "name"):
            val = s.name
        elif isinstance(s, dict) and "name" in s:
            val = s["name"]
        else:
            val = str(s)
        val_clean = val.strip().lower()
        if val_clean:
            result.add(val_clean)
    return result


def compute_skill_overlaps(
    candidate_hard: Set[str],
    candidate_soft: Set[str],
    job_hard_names: List[str],
    job_soft_names: List[str],
    job_nice_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calculate matched and missing skill lists and overlap ratios.
    """
    job_nice_names = job_nice_names or []

    # Hard skills
    matched_hard = [name for name in job_hard_names if name.strip().lower() in candidate_hard]
    missing_hard = [name for name in job_hard_names if name.strip().lower() not in candidate_hard]

    # Soft skills
    matched_soft = [name for name in job_soft_names if name.strip().lower() in candidate_soft]
    missing_soft = [name for name in job_soft_names if name.strip().lower() not in candidate_soft]

    # Nice to have skills
    missing_nice = [name for name in job_nice_names if name.strip().lower() not in candidate_hard]

    # Ratios
    hard_overlap_ratio = (
        len(matched_hard) / max(1, len(job_hard_names)) if job_hard_names else 0.5
    )
    soft_overlap_ratio = (
        len(matched_soft) / max(1, len(job_soft_names)) if job_soft_names else 0.8
    )

    return {
        "matched_hard": matched_hard,
        "missing_hard": missing_hard,
        "matched_soft": matched_soft,
        "missing_soft": missing_soft,
        "missing_nice": missing_nice,
        "hard_overlap_ratio": max(0.0, min(1.0, hard_overlap_ratio)),
        "soft_overlap_ratio": max(0.0, min(1.0, soft_overlap_ratio)),
    }


def calculate_composite_fit_score(
    hard_overlap_ratio: float,
    soft_overlap_ratio: float,
    vector_similarity: float,
) -> float:
    """
    Compute composite candidate-to-job fit score according to SPEC §3.5:
    Fit Score = 0.50 * HardSkillOverlap + 0.20 * SoftSkillOverlap + 0.30 * VectorSimilarity
    Returns percentage between 0.0 and 100.0 rounded to 1 decimal place.
    """
    h_ratio = max(0.0, min(1.0, hard_overlap_ratio))
    s_ratio = max(0.0, min(1.0, soft_overlap_ratio))
    v_sim = max(0.0, min(1.0, vector_similarity))

    composite = (0.50 * h_ratio) + (0.20 * s_ratio) + (0.30 * v_sim)
    return round(composite * 100.0, 1)


class CandidateMatcherService:
    """
    High-level orchestrator for candidate CV ingestion, feature extraction cascade,
    taxonomy alignment, and multi-region job gap analysis.
    """

    @classmethod
    def parse_and_extract_candidate(
        cls,
        resume_text: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Extract skills from resume using Phase 2 Cascade and normalize with Phase 3 Taxonomy.
        """
        # 1. Multi-tier cascade extraction
        extracted = extract_cascade(resume_text)

        # 2. Canonical taxonomy normalization
        raw_hard = extracted.get("hard_skills") or []
        normalized_items = normalize_skills(raw_hard, db=db)
        canonical_hard_skills = [item.canonical_name for item in normalized_items]

        extracted["canonical_hard_skills"] = canonical_hard_skills
        return extracted

    @classmethod
    def match_resume(
        cls,
        resume_text: str,
        db: Session,
        target_region: Optional[str] = None,
        seniority: Optional[str] = None,
        workplace_type: Optional[str] = None,
        limit: int = 10,
        min_fit_score: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Match candidate resume text against job database with full gap analysis.
        """
        cleaned_text = (resume_text or "").strip()
        if not cleaned_text:
            raise ValueError("Resume text cannot be empty")

        # 1. Extract and canonicalize candidate profile
        extracted = cls.parse_and_extract_candidate(cleaned_text, db=db)
        candidate_hard = _extract_skill_set(extracted.get("canonical_hard_skills") or extracted.get("hard_skills"))
        candidate_soft = _extract_skill_set(extracted.get("soft_skills"))

        # 2. Compute candidate dense vector embedding
        candidate_vec = embed_resume_text(cleaned_text, extracted_skills=extracted)

        # 3. Query candidate jobs with filters
        query = select(Job)
        if target_region and target_region.lower() != "global":
            query = query.where(Job.region.ilike(f"%{target_region.strip()}%"))
        if seniority:
            query = query.where(Job.seniority.ilike(f"%{seniority.strip()}%"))
        if workplace_type:
            query = query.where(Job.workplace_type.ilike(f"%{workplace_type.strip()}%"))

        jobs = db.scalars(query.limit(200)).all()
        evaluated_count = len(jobs)

        scored_matches: List[Dict[str, Any]] = []
        missing_skill_counter: Counter = Counter()

        # 4. Evaluate each job
        for job in jobs:
            job_hard_names = [s.name for s in (job.hard_skills or [])]
            job_soft_names = [s.name for s in (job.soft_skills or [])]
            job_nice_names = [s.name for s in (job.nice_to_have_skills or [])]

            # Compute skill overlaps
            overlaps = compute_skill_overlaps(
                candidate_hard=candidate_hard,
                candidate_soft=candidate_soft,
                job_hard_names=job_hard_names,
                job_soft_names=job_soft_names,
                job_nice_names=job_nice_names,
            )

            # Compute dense vector similarity
            job_vec = job.embedding if getattr(job, "embedding", None) is not None else embed_job(job)
            if isinstance(job_vec, list) and job_vec:
                vec_sim = cosine_similarity(candidate_vec, job_vec)
            else:
                vec_sim = 0.5

            # Calculate composite fit score: 0.50*Hard + 0.20*Soft + 0.30*Vector
            fit_score = calculate_composite_fit_score(
                hard_overlap_ratio=overlaps["hard_overlap_ratio"],
                soft_overlap_ratio=overlaps["soft_overlap_ratio"],
                vector_similarity=vec_sim,
            )

            for missing_s in overlaps["missing_hard"]:
                missing_skill_counter[missing_s] += 1

            if fit_score >= min_fit_score:
                loc_str = ", ".join(
                    filter(None, [job.city.name if job.city else None, job.state.name if job.state else None])
                ) or None

                scored_matches.append({
                    "job_id": job.id,
                    "job_title": job.job_title,
                    "company": job.company.name if job.company else None,
                    "location": loc_str,
                    "region": job.region or "Latin America",
                    "salary": job.salary,
                    "currency": job.currency or "BRL",
                    "workplace_type": job.workplace_type,
                    "fit_score": fit_score,
                    "hard_skill_overlap": round(overlaps["hard_overlap_ratio"] * 100.0, 1),
                    "soft_skill_overlap": round(overlaps["soft_overlap_ratio"] * 100.0, 1),
                    "vector_similarity": round(vec_sim * 100.0, 1),
                    "gap_analysis": {
                        "matched_hard_skills": overlaps["matched_hard"],
                        "missing_hard_skills": overlaps["missing_hard"],
                        "matched_soft_skills": overlaps["matched_soft"],
                        "missing_soft_skills": overlaps["missing_soft"],
                        "matched_skills": overlaps["matched_hard"] + overlaps["matched_soft"],
                        "missing_critical_skills": overlaps["missing_hard"],
                        "missing_nice_to_have": overlaps["missing_nice"] + overlaps["missing_soft"],
                        "recommended_skills": [],
                    },
                })

        # Sort descending by fit score
        scored_matches.sort(key=lambda m: m["fit_score"], reverse=True)
        top_matches = scored_matches[:limit]

        # 5. Populate recommended high-ROI skills across top matching roles
        top_recommended = [skill for skill, _ in missing_skill_counter.most_common(5)]
        for match in top_matches:
            match["gap_analysis"]["recommended_skills"] = top_recommended

        return {
            "extracted_skills": {
                "hard_skills": extracted.get("canonical_hard_skills") or extracted.get("hard_skills") or [],
                "soft_skills": extracted.get("soft_skills") or [],
                "tech_stack": extracted.get("tech_stack") or [],
            },
            "target_region": target_region,
            "total_evaluated": evaluated_count,
            "total_matches": len(top_matches),
            "matches": top_matches,
        }
