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
    # Ratios (0.0 if job specifies no requirements)
    hard_overlap_ratio = (
        len(matched_hard) / len(job_hard_names) if job_hard_names else 0.0
    )
    soft_overlap_ratio = (
        len(matched_soft) / len(job_soft_names) if job_soft_names else 0.0
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
        raw_text: str,
        engine: str = "cascade",
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured skills, seniority, years of experience, and taxonomies
        from raw candidate resume text.
        """
        from services.extractor_service import extract_cascade, normalise_skill_label
        from services.taxonomy_service import normalize_skills

        cleaned = (raw_text or "").strip()
        if not cleaned:
            raise ValueError("Resume text cannot be empty")

        extracted = extract_cascade(cleaned)
        hard_skills = extracted.get("hard_skills") or []
        soft_skills = extracted.get("soft_skills") or []
        tech_stack = extracted.get("tech_stack") or hard_skills

        # Normalize canonical names
        if db is not None:
            normalized_items = normalize_skills(hard_skills, db=db)
            canonical_hard = [item.canonical_name for item in normalized_items]
        else:
            canonical_hard = [normalise_skill_label(s) for s in hard_skills]

        return {
            "name": extracted.get("name"),
            "seniority": extracted.get("seniority") or "Mid",
            "years_experience": extracted.get("years_experience") or 3,
            "hard_skills": hard_skills,
            "canonical_hard_skills": canonical_hard,
            "soft_skills": soft_skills,
            "tech_stack": tech_stack,
            "salary": extracted.get("salary"),
            "confidence_score": extracted.get("confidence_score", 0.8),
        }

    @classmethod
    def match_resume(
        cls,
        resume_text: str,
        db: Session,
        target_region: Optional[str] = None,
        seniority: Optional[str] = None,
        limit: int = 10,
        min_fit_score: float = 0.0,
    ) -> Dict[str, Any]:
        """
        End-to-end candidate CV matcher against structured pgvector Job entities.
        Computes composite fit scores, skill overlaps, and gap analyses.
        """
        from entities import Job
        from services.embedding_service import cosine_similarity, embed_candidate, embed_job

        # 1. Extract candidate profile
        extracted = cls.parse_and_extract_candidate(resume_text, db=db)
        candidate_hard = set(s.strip().lower() for s in (extracted.get("canonical_hard_skills") or extracted.get("hard_skills") or []))
        candidate_soft = set(s.strip().lower() for s in (extracted.get("soft_skills") or []))

        # 2. Dense semantic embedding for candidate
        candidate_vec = embed_candidate(extracted)

        # 3. Query candidate database jobs
        query = select(Job)
        if target_region and target_region.lower() not in ("global", "all"):
            query = query.where(Job.region.ilike(f"%{target_region.strip()}%"))
        if seniority:
            query = query.where(Job.seniority.ilike(f"%{seniority.strip()}%"))

        jobs = db.scalars(query.limit(200)).all()
        evaluated_count = len(jobs)

        # 4. Score each job against candidate
        scored_matches: List[Dict[str, Any]] = []
        missing_skill_counter: Counter[str] = Counter()

        for job in jobs:
            job_hard_names = [s.name for s in (job.hard_skills or [])]
            job_soft_names = [s.name for s in (job.soft_skills or [])]
            job_nice_names = [s.name for s in (job.nice_to_have_skills or [])]

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

        # 5. Populate recommended high-ROI skills tailored to each matching role
        for match in top_matches:
            job_missing = match["gap_analysis"]["missing_hard_skills"]
            recommended = sorted(
                job_missing,
                key=lambda s: missing_skill_counter.get(s, 0),
                reverse=True,
            )
            for s, _ in missing_skill_counter.most_common(5):
                if s not in recommended:
                    recommended.append(s)
            match["gap_analysis"]["recommended_skills"] = recommended[:5]

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
