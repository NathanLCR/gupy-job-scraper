from collections import defaultdict
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from database import get_sync_db
from entities import HardSkill, Job
from entities.associations import job_hard_skills
from schemas import (
    SkillAnalyticsResponse,
    SkillDemandItem,
    SkillGraphResponse,
    SkillNormalizeRequest,
    SkillNormalizeResponse,
    TaxonomyListResponse,
    TechTrendsResponse,
)
from services.cooccurrence_service import compute_cooccurrence_graph
from services.features_service_hm import (
    get_average_salary,
    get_jobs_by_contract_type,
    get_jobs_by_seniority,
    get_technology_trends,
    get_top_locations,
)
from services.taxonomy_service import (
    get_taxonomy_tree,
    normalize_skill,
    normalize_skills,
    seed_default_taxonomy,
)

router = APIRouter(prefix="/analytics", tags=["Market Analytics & Graph"])


@router.get("/skills", response_model=SkillAnalyticsResponse)
def get_skills_analytics(
    region: Optional[str] = Query(None, description="Filter analytics by region"),
    limit: int = Query(15, ge=1, le=50, description="Top skills count"),
    db: Session = Depends(get_sync_db),
):
    """
    Retrieve aggregate market demand, salary correlation, and top technology requirements.
    Canonicalizes skills using ESCO/O*NET taxonomy normalization.
    """
    # 1. Base jobs query with region filter
    job_query = select(Job)
    if region and region.lower() != "all":
        job_query = job_query.where(Job.region == region)

    jobs = db.scalars(job_query).all()
    total_jobs = len(jobs)

    # 2. Aggregate skill counts and salary sums
    skill_counts = defaultdict(int)
    skill_salaries = defaultdict(list)

    for job in jobs:
        # Collect skills from hard_skills and tech_stack
        job_skills = set()
        if job.hard_skills:
            for s in job.hard_skills:
                norm = normalize_skill(s.name, db=db)
                job_skills.add(norm.canonical_name)
        if job.tech_stack:
            for t in job.tech_stack:
                norm = normalize_skill(t, db=db)
                job_skills.add(norm.canonical_name)

        for skill_name in job_skills:
            skill_counts[skill_name] += 1
            if job.salary and job.salary > 0:
                skill_salaries[skill_name].append(job.salary)

    sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    demand_items = []
    for name, count in sorted_skills:
        meta = normalize_skill(name, db=db)
        salaries = skill_salaries.get(name, [])
        avg_sal = round(sum(salaries) / len(salaries), 2) if salaries else None
        pct = round((count / max(1, total_jobs)) * 100, 1)

        demand_items.append(
            SkillDemandItem(
                name=name,
                count=count,
                percentage=pct,
                avg_salary=avg_sal,
                category=meta.category,
            )
        )

    top_locs = get_top_locations(n=5)
    contract_data = get_jobs_by_contract_type()
    seniority_data = get_jobs_by_seniority()

    return SkillAnalyticsResponse(
        total_jobs=total_jobs,
        top_skills=demand_items,
        top_locations=top_locs,
        salary_by_seniority=seniority_data,
        contract_types=contract_data,
        region=region,
    )


@router.get("/graph", response_model=SkillGraphResponse)
def get_skill_cooccurrence_graph(
    min_weight: int = Query(1, ge=1, description="Minimum co-occurrence weight threshold"),
    min_lift: float = Query(0.0, ge=0.0, description="Minimum statistical lift threshold"),
    max_nodes: int = Query(30, ge=5, le=100, description="Max skill nodes in graph"),
    region: Optional[str] = Query(None, description="Optional region filter"),
    db: Session = Depends(get_sync_db),
):
    """
    Compute pairwise skill co-occurrence network data with Support & Lift statistical metrics.
    Returns nodes (skills sized by frequency), edges (with weight, lift, and support), and clusters.
    """
    return compute_cooccurrence_graph(
        db=db,
        min_weight=min_weight,
        min_lift=min_lift,
        max_nodes=max_nodes,
        region=region,
    )


@router.get("/taxonomies", response_model=TaxonomyListResponse)
def get_taxonomies(
    db: Session = Depends(get_sync_db),
):
    """
    Retrieve standard ESCO / O*NET hierarchical taxonomy categories and tree nodes.
    """
    tree = get_taxonomy_tree(db)
    total_nodes = sum(1 + len(cat.children) for cat in tree)
    return TaxonomyListResponse(categories=tree, total_nodes=total_nodes)


@router.post("/taxonomy/normalize", response_model=SkillNormalizeResponse)
def normalize_skills_endpoint(
    body: SkillNormalizeRequest,
    db: Session = Depends(get_sync_db),
):
    """
    Normalize raw skill names to canonical ESCO / O*NET entities with taxonomy categories.
    """
    results = normalize_skills(body.skills, db=db)
    return SkillNormalizeResponse(normalized=results)


@router.get("/trends", response_model=TechTrendsResponse)
def get_trends(
    days: int = Query(30, ge=7, le=90, description="Time series window in days"),
    limit: int = Query(5, ge=1, le=10, description="Number of top technologies"),
    skill: Optional[str] = Query(None, description="Specific technology to isolate"),
):
    """Retrieve technology demand time-series trend curves."""
    result = get_technology_trends(days=days, limit=limit, skill=skill)
    return result


@router.get("/locations")
def get_locations(limit: int = Query(10, ge=1, le=50)):
    """Retrieve top hiring cities/locations."""
    return get_top_locations(n=limit)


@router.get("/salary")
def get_salary_analytics():
    """Retrieve average salary metrics."""
    avg_salary = get_average_salary()
    return {"average_salary": avg_salary}


@router.get("/contract-types")
def get_contract_types():
    """Retrieve job distribution by contract type."""
    return get_jobs_by_contract_type()


@router.get("/seniority")
def get_seniority_distribution():
    """Retrieve job distribution by seniority level."""
    return get_jobs_by_seniority()
