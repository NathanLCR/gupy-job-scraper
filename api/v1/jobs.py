import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from database import get_sync_db
from entities import Job, JobPost, Company, City, State, HardSkill
from entities.associations import job_hard_skills
from schemas import (
    HybridSearchItem,
    HybridSearchRequest,
    HybridSearchResponse,
    JobFilterParams,
    JobIngestRequest,
    JobListResponse,
    JobPostListResponse,
    JobPostResponse,
    JobResponse,
    PaginationMeta,
    TaskStatusResponse,
)
from services.csv_service import export_job_posts_csv, export_jobs_csv
from services.hybrid_search_service import hybrid_search_jobs
from services.job_service_hm import get_job, get_jobs
from services.jobs_post_service_hm import get_job_post, get_jobs_posts
from services.scraper_service_hm import start_scrape_thread

router = APIRouter(prefix="/jobs", tags=["Jobs & Ingestion"])


@router.get("", response_model=JobListResponse)
def list_jobs(
    search: Optional[str] = Query(None, description="Search keyword in title, company, or skills"),
    location: Optional[str] = Query(None, description="Filter by city or state"),
    region: Optional[str] = Query(None, description="Filter by region (e.g. Europe, Latin America)"),
    country_code: Optional[str] = Query(None, description="Filter by ISO country code (e.g. IE, BR)"),
    workplace_type: Optional[str] = Query(None, description="REMOTE, HYBRID, ONSITE"),
    seniority: Optional[str] = Query(None, description="Seniority level (Junior, Pleno, Senior)"),
    sort: str = Query("id", description="Sort column (id, title, company, salary, location)"),
    order: str = Query("desc", description="Sort direction (asc, desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """Retrieve paginated list of processed jobs with multi-region and taxonomy filters."""
    result = get_jobs(
        search=search,
        location=location,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        paginated=True,
    )
    return result


@router.post("/search/hybrid", response_model=HybridSearchResponse)
def search_jobs_hybrid(
    request: HybridSearchRequest,
    db: Session = Depends(get_sync_db),
):
    """
    Reciprocal Rank Fusion (RRF, k=60) Hybrid Search combining dense vector
    cosine similarity (Job.embedding) and sparse full-text lexical ranking.
    """
    results = hybrid_search_jobs(
        query=request.query,
        db=db,
        region=request.region,
        country_code=request.country_code,
        workplace_type=request.workplace_type,
        seniority=request.seniority,
        min_salary=request.min_salary,
        max_salary=request.max_salary,
        skill=request.skill,
        location=request.location,
        top_k=request.top_k,
        dense_weight=request.dense_weight,
        sparse_weight=request.sparse_weight,
    )

    items = [
        HybridSearchItem(
            job_id=r.job_id,
            job=JobResponse.model_validate(r.job_dict or (r.job.to_dict() if r.job else {})),
            rrf_score=r.rrf_score,
            dense_score=r.dense_score,
            sparse_score=r.sparse_score,
            dense_rank=r.dense_rank,
            sparse_rank=r.sparse_rank,
            normalized_score=r.normalized_score,
        )
        for r in results
    ]

    return HybridSearchResponse(
        query=request.query,
        total_results=len(items),
        items=items,
    )


@router.get("/export")
def export_processed_jobs():
    """Export all processed jobs as CSV."""
    csv_data = export_jobs_csv()
    return Response(
        content=csv_data.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs.csv"},
    )


@router.get("/posts", response_model=JobPostListResponse)
def list_raw_job_posts(
    search: Optional[str] = Query(None, description="Search text in raw job posts"),
    workplace_type: Optional[str] = Query(None, description="Workplace type filter"),
    sort: str = Query("published_date", description="Sort field"),
    order: str = Query("desc", description="Sort order"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Retrieve paginated raw job posts from ingestion feeds."""
    result = get_jobs_posts(
        search=search,
        workplace_type=workplace_type,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        paginated=True,
    )
    return result


@router.get("/posts/export")
def export_raw_job_posts():
    """Export raw job posts as CSV."""
    csv_data = export_job_posts_csv()
    return Response(
        content=csv_data.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=job_posts.csv"},
    )


@router.get("/posts/{id}", response_model=JobPostResponse)
def get_raw_job_post_by_id(id: int):
    """Retrieve a single raw job post by its ID."""
    try:
        post = get_job_post(id)
        return post.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{id}", response_model=JobResponse)
def get_job_by_id(id: int):
    """Retrieve detailed processed job with extracted skills and taxonomy data."""
    try:
        job = get_job(id)
        return job.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/ingest", response_model=TaskStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job_ingestion(request: JobIngestRequest):
    """Trigger background job scraping/ingestion adapter task."""
    task_id = f"ingest_{uuid.uuid4().hex[:12]}"
    # Start ingestion thread (or Celery task when worker is connected)
    start_scrape_thread()
    return TaskStatusResponse(
        task_id=task_id,
        status="PENDING",
        result={"source": request.source, "term": request.term, "region": request.region},
    )
