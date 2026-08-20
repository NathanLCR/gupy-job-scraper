"""
Skill Co-occurrence Graph Engine.
Computes pairwise skill frequencies, Support, Lift metrics, and clustering payloads.
"""

from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from entities import HardSkill, Job, SkillCooccurrence
from entities.associations import job_hard_skills
from schemas.analytics import (
    ClusterInfo,
    GraphEdge,
    GraphNode,
    SkillGraphResponse,
)
from services.taxonomy_service import normalize_skill


def compute_metrics(
    count_ab: int,
    count_a: int,
    count_b: int,
    total_jobs: int,
) -> Tuple[float, float]:
    """
    Computes Support and Lift metrics for a pair of skills (A, B).
    Support(A, B) = P(A ∩ B) = count(A ∩ B) / N
    Lift(A, B) = P(A ∩ B) / (P(A) * P(B)) = (count(A ∩ B) * N) / (count(A) * count(B))
    """
    if total_jobs <= 0 or count_a <= 0 or count_b <= 0:
        return 0.0, 0.0

    support = count_ab / total_jobs
    lift = (count_ab * total_jobs) / (count_a * count_b)
    return round(support, 4), round(lift, 3)


def extract_skills_from_job(job: Job) -> Set[str]:
    """Extracts deduplicated canonical skills from a Job entity."""
    skills = set()
    if job.hard_skills:
        for s in job.hard_skills:
            norm = normalize_skill(s.name)
            skills.add(norm.canonical_name)
    if job.tech_stack:
        for t in job.tech_stack:
            norm = normalize_skill(t)
            skills.add(norm.canonical_name)
    return skills


def compute_cooccurrence_graph(
    db: Session,
    min_weight: int = 1,
    min_lift: float = 0.0,
    max_nodes: int = 30,
    region: Optional[str] = None,
) -> SkillGraphResponse:
    """
    Computes skill co-occurrence network data, Support & Lift metrics, and cluster summaries.
    """
    # 1. Fetch relevant jobs
    query = select(Job)
    if region and region.lower() != "all":
        query = query.where(Job.region == region)

    jobs = db.scalars(query).all()
    total_jobs = len(jobs)

    if total_jobs == 0:
        return SkillGraphResponse(
            nodes=[],
            edges=[],
            total_skills=0,
            total_connections=0,
            clusters=[],
        )

    # 2. Count individual skill frequencies and pairwise co-occurrences
    skill_counts: Dict[str, int] = defaultdict(int)
    pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)

    for job in jobs:
        job_skills = extract_skills_from_job(job)
        for s in job_skills:
            skill_counts[s] += 1

        if len(job_skills) >= 2:
            sorted_skills = sorted(job_skills)
            for s1, s2 in combinations(sorted_skills, 2):
                pair_counts[(s1, s2)] += 1

    # 3. Select top skills bounded by max_nodes
    sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
    top_skills = sorted_skills[:max_nodes]
    top_skill_names = {s[0] for s in top_skills}

    # 4. Build Nodes
    nodes: List[GraphNode] = []
    category_clusters: Dict[str, List[str]] = defaultdict(list)

    for name, count in top_skills:
        meta = normalize_skill(name, db=db)
        cat = meta.category
        category_clusters[cat].append(name)

        nodes.append(
            GraphNode(
                id=name,
                label=name,
                category=cat,
                value=count,
                cluster=cat,
                esco_uri=meta.esco_uri,
                onet_code=meta.onet_code,
            )
        )

    # 5. Build Edges with Weight, Support, and Lift
    edges: List[GraphEdge] = []
    for (s1, s2), weight in pair_counts.items():
        if s1 in top_skill_names and s2 in top_skill_names:
            if weight >= min_weight:
                support, lift = compute_metrics(
                    count_ab=weight,
                    count_a=skill_counts[s1],
                    count_b=skill_counts[s2],
                    total_jobs=total_jobs,
                )
                if lift >= min_lift:
                    edges.append(
                        GraphEdge(
                            source=s1,
                            target=s2,
                            weight=weight,
                            lift=lift,
                            support=support,
                        )
                    )

    # Sort edges by weight descending
    edges.sort(key=lambda e: e.weight, reverse=True)

    # 6. Build Clusters
    clusters: List[ClusterInfo] = [
        ClusterInfo(
            name=cat,
            size=len(members),
            skills=sorted(members),
        )
        for cat, members in category_clusters.items()
    ]
    clusters.sort(key=lambda c: c.size, reverse=True)

    return SkillGraphResponse(
        nodes=nodes,
        edges=edges,
        total_skills=len(nodes),
        total_connections=len(edges),
        clusters=clusters,
    )


def sync_cooccurrences_to_db(db: Session, region: str = "Global") -> int:
    """
    Computes pairwise co-occurrences across jobs and persists them into SkillCooccurrence table.
    """
    query = select(Job)
    if region != "Global":
        query = query.where(Job.region == region)

    jobs = db.scalars(query).all()
    pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)

    for job in jobs:
        job_skills = extract_skills_from_job(job)
        if len(job_skills) >= 2:
            for s1, s2 in combinations(sorted(job_skills), 2):
                pair_counts[(s1, s2)] += 1

    records_synced = 0
    for (s1, s2), count in pair_counts.items():
        pair_key = f"{s1}__{s2}__{region}"
        existing = db.scalar(
            select(SkillCooccurrence).where(SkillCooccurrence.pair_key == pair_key)
        )
        if existing:
            existing.cooccurrence_count = count
        else:
            record = SkillCooccurrence(
                skill_a=s1,
                skill_b=s2,
                pair_key=pair_key,
                cooccurrence_count=count,
                region=region,
            )
            db.add(record)
        records_synced += 1

    db.commit()
    return records_synced
