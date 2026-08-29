"""
SkillPulse AI Candidate Matcher & Skill Gap Analysis Service.
Coordinates resume parsing, multi-tier cascade extraction, canonical taxonomy mapping,
composite fit score calculation (0.50*Hard + 0.20*Soft + 0.30*Vector),
and granular gap breakdown with upskilling recommendations (SPEC §3.5).
"""

from collections import Counter
import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from database import SessionLocal
from entities import CandidateProfile, HardSkill, Job, NiceToHaveSkill, SoftSkill
from services.embedding_service import (
    cosine_similarity,
    embed_job,
    embed_resume_text,
)
from services.extractor_service import extract_cascade
from services.taxonomy_service import normalize_skills
from config import settings
from services.embedding_service import embed_query_checked
from services.postgres_retrieval_service import (
    PostgresRetrievalService,
    RetrievalFilters,
)

logger = logging.getLogger(__name__)


def build_candidate_lexical_query(
    hard_skills: Sequence[str],
    tech_stack: Sequence[str],
    seniority: Optional[str],
) -> str:
    """Build stable canonical terms without candidate prose or personal data."""
    labels: dict[str, str] = {}
    for value in list(hard_skills) + list(tech_stack):
        cleaned = str(value).strip()
        if cleaned:
            labels.setdefault(cleaned.casefold(), cleaned)
    if seniority and seniority.strip():
        labels.setdefault(seniority.strip().casefold(), seniority.strip())
    return " ".join(sorted(labels.values(), key=str.casefold))


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
        from services.embedding_service import cosine_similarity

        # 1. Extract candidate profile
        extracted = cls.parse_and_extract_candidate(resume_text, db=db)
        candidate_hard = set(s.strip().lower() for s in (extracted.get("canonical_hard_skills") or extracted.get("hard_skills") or []))
        candidate_soft = set(s.strip().lower() for s in (extracted.get("soft_skills") or []))

        # 2. Produce exactly one candidate vector and retain its provenance.
        candidate_embedding = embed_query_checked(resume_text)
        candidate_vec = candidate_embedding.vector

        # 3. Query candidate database jobs
        query = select(Job)
        eligible_query = select(func.count(Job.id))
        if target_region and target_region.lower() not in ("global", "all"):
            query = query.where(Job.region.ilike(f"%{target_region.strip()}%"))
            eligible_query = eligible_query.where(Job.region.ilike(f"%{target_region.strip()}%"))
        if seniority:
            query = query.where(Job.seniority.ilike(f"%{seniority.strip()}%"))
            eligible_query = eligible_query.where(Job.seniority.ilike(f"%{seniority.strip()}%"))

        total_eligible = int(db.scalar(eligible_query) or 0)
        if settings.POSTGRES_INDEXED_RETRIEVAL_ENABLED:
            lexical_query = build_candidate_lexical_query(
                extracted.get("canonical_hard_skills") or extracted.get("hard_skills") or [],
                extracted.get("tech_stack") or [],
                seniority,
            )
            retrieval = PostgresRetrievalService(db).retrieve(
                lexical_query,
                RetrievalFilters(region=target_region, seniority=seniority),
                top_k=300,
                dense_pool_size=200,
                lexical_pool_size=200,
                max_candidates=300,
                query_embedding=candidate_embedding,
            )
            candidate_ids = [candidate.job_id for candidate in retrieval.candidates]
            if candidate_ids:
                selected = db.scalars(
                    select(Job).where(Job.id.in_(candidate_ids))
                ).unique().all()
                by_id = {job.id: job for job in selected}
                jobs = [by_id[job_id] for job_id in candidate_ids if job_id in by_id]
            else:
                jobs = []
        else:
            jobs = db.scalars(query.limit(200)).unique().all()
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
            job_vec = getattr(job, "embedding", None)
            semantic_available = (
                job_vec is not None
                and getattr(job, "embedding_model", None) == candidate_embedding.model
            )
            vec_sim = (
                cosine_similarity(candidate_vec, list(job_vec))
                if semantic_available
                else 0.0
            )

            # Calculate composite fit score: 0.50*Hard + 0.20*Soft + 0.30*Vector
            fit_score = calculate_composite_fit_score(
                hard_overlap_ratio=overlaps["hard_overlap_ratio"],
                soft_overlap_ratio=overlaps["soft_overlap_ratio"],
                vector_similarity=vec_sim,
            )

            hard_pts = round(overlaps["hard_overlap_ratio"] * 50.0, 1)
            soft_pts = round(overlaps["soft_overlap_ratio"] * 20.0, 1)
            vector_pts = round(vec_sim * 30.0, 1)
            total_pts = round(hard_pts + soft_pts + vector_pts, 1)

            # Generate concise, human-readable match reason
            total_req = len(job_hard_names)
            matched_count = len(overlaps["matched_hard"])
            sim_pct = int(round(vec_sim * 100))
            if total_req > 0:
                skill_rationale = f"{matched_count}/{total_req} required technical skills matched."
            else:
                skill_rationale = "Aligned with role tech stack requirements."

            if not semantic_available:
                semantic_rationale = "Semantic evidence unavailable."
            elif vec_sim >= 0.70:
                semantic_rationale = f"Strong semantic similarity ({sim_pct}%) with role domain."
            else:
                semantic_rationale = f"Semantic similarity measured at {sim_pct}%."
            match_reason = f"{semantic_rationale} {skill_rationale}"
            if overlaps["matched_hard"]:
                match_reason += f" Matched: {', '.join(overlaps['matched_hard'][:3])}."
            if overlaps["missing_hard"]:
                match_reason += f" Missing: {', '.join(overlaps['missing_hard'][:2])}."

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
                    "hard_points": hard_pts,
                    "soft_points": soft_pts,
                    "vector_points": vector_pts,
                    "total_points": total_pts,
                    "match_reason": match_reason,
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
        scored_matches.sort(key=lambda m: (-m["fit_score"], m["job_id"]))
        qualified_count = len(scored_matches)
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

        # 6. Candidate domain area strengths & market summary
        domain_categories = {
            "Backend Engineering": ["python", "go", "java", "node.js", "c#", "rust", "fastapi", "django", "flask", "spring", "express", "microservices", "rest apis", "graphql", "grpc", "celery"],
            "Databases & Storage": ["postgresql", "mysql", "redis", "mongodb", "elasticsearch", "sql", "cassandra", "dynamodb", "oracle", "sqlite"],
            "Cloud & DevOps": ["kubernetes", "docker", "aws", "gcp", "azure", "terraform", "ci/cd", "linux", "helm", "prometheus", "grafana", "ansible", "git"],
            "Machine Learning & AI": ["pytorch", "tensorflow", "scikit-learn", "pandas", "numpy", "hugging face", "langchain", "rag", "pgvector", "llm", "mlops", "transformers", "nlp"],
            "Frontend & Web": ["react", "typescript", "javascript", "vue", "angular", "next.js", "html5", "css3", "tailwindcss", "redux"],
        }

        strongest_areas = []
        for area_name, area_skills in domain_categories.items():
            matched_in_cat = [s for s in area_skills if s in candidate_hard]
            if matched_in_cat:
                ratio = min(1.0, len(matched_in_cat) / max(2, len(area_skills) * 0.4))
                score_pct = round(60.0 + (ratio * 38.0), 0)
            else:
                score_pct = 40.0
            strongest_areas.append({"area": area_name, "score": int(score_pct), "matched": matched_in_cat})

        strongest_areas.sort(key=lambda x: x["score"], reverse=True)

        largest_gaps = [s for s, _ in missing_skill_counter.most_common(6) if s.lower() not in candidate_hard][:5]
        if not largest_gaps and missing_skill_counter:
            largest_gaps = [s for s, _ in missing_skill_counter.most_common(5)][:5]

        overall_fit = top_matches[0]["fit_score"] if top_matches else 0.0

        candidate_summary = {
            "overall_fit_score": overall_fit,
            "extracted_seniority": extracted.get("seniority") or "Mid",
            "years_experience": extracted.get("years_experience") or 3,
            "strongest_areas": strongest_areas,
            "largest_gaps": largest_gaps,
        }

        return {
            "extracted_skills": {
                "hard_skills": extracted.get("canonical_hard_skills") or extracted.get("hard_skills") or [],
                "soft_skills": extracted.get("soft_skills") or [],
                "tech_stack": extracted.get("tech_stack") or [],
            },
            "candidate_summary": candidate_summary,
            "target_region": target_region,
            "total_eligible": total_eligible,
            "total_evaluated": evaluated_count,
            "total_qualified": qualified_count,
            "total_matches": len(top_matches),
            "matches": top_matches,
        }

    @classmethod
    def explain_fit_and_gaps(
        cls,
        resume_text: str,
        job_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Generate explainable breakdown and AI narrative for a candidate's fit against a specific job.
        Keeps scoring 100% deterministic while providing optional coaching narrative.
        """
        job = db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found")

        extracted = cls.parse_and_extract_candidate(resume_text, db=db)
        candidate_hard = set(s.lower() for s in (extracted.get("canonical_hard_skills") or extracted.get("hard_skills") or []))
        candidate_soft = set(s.lower() for s in (extracted.get("soft_skills") or []))

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

        cand_vector = embed_resume_text(resume_text, extracted_skills=extracted)
        job_vector = embed_job(job)
        vec_sim = max(0.0, cosine_similarity(cand_vector, job_vector))

        fit_score = calculate_composite_fit_score(
            hard_overlap_ratio=overlaps["hard_overlap_ratio"],
            soft_overlap_ratio=overlaps["soft_overlap_ratio"],
            vector_similarity=vec_sim,
        )

        # Generate narrative via LLMExtractionService with SHA-256 caching
        from features_extractors.llm_extractor import LLMExtractionService

        context = (
            f"Candidate Hard Skills: {', '.join(sorted(candidate_hard))}\n"
            f"Job: {job.job_title} at {getattr(job.company, 'name', 'Tech Company')}\n"
            f"Job Required Hard Skills: {', '.join(job_hard_names)}\n"
            f"Fit Score: {fit_score}%\n"
            f"Matched Hard Skills: {', '.join(overlaps['matched_hard'])}\n"
            f"Missing Hard Skills: {', '.join(overlaps['missing_hard'])}"
        )

        narrative = LLMExtractionService.explain_gaps(context, db=db)
        if not narrative or narrative.startswith("Perfil analisado"):
            # Clean deterministic fallback template
            if overlaps["missing_hard"]:
                missing_str = ", ".join(overlaps["missing_hard"][:3])
                narrative = (
                    f"Seu perfil possui forte alinhamento ({fit_score}%) com as competências técnicas da vaga. "
                    f"Para maximizar suas chances para a posição de {job.job_title}, foque em aprofundar conhecimentos em {missing_str}."
                )
            else:
                narrative = f"Excelente alinhamento ({fit_score}%). Suas competências cobrem integralmente os requisitos técnicos essenciais exigidos para {job.job_title}."

        company_name = job.company.name if job.company and hasattr(job.company, "name") else None

        return {
            "job_id": job.id,
            "job_title": job.job_title,
            "company": company_name,
            "fit_score": fit_score,
            "hard_skill_overlap": round(overlaps["hard_overlap_ratio"] * 100.0, 1),
            "soft_skill_overlap": round(overlaps["soft_overlap_ratio"] * 100.0, 1),
            "vector_similarity": round(vec_sim * 100.0, 1),
            "matched_hard_skills": overlaps["matched_hard"],
            "missing_hard_skills": overlaps["missing_hard"],
            "recommended_upskilling": overlaps["missing_hard"][:5],
            "explanation": narrative,
        }

