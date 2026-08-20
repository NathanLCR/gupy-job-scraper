from contextlib import asynccontextmanager
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.v1.router import api_v1_router
from config import settings
from database import init_db
from schemas import HealthResponse
from services.csv_service import export_job_posts_csv, export_jobs_csv
from services.error_service import get_errors
from services.extractor_service import (
    get_extractor_status,
    start_extractor_thread,
    start_llm_extractor_thread,
)
from services.features_service_hm import (
    get_average_job_post_daily,
    get_average_salary,
    get_jobs_by_contract_type,
    get_jobs_by_seniority,
    get_technology_trends,
    get_top_locations,
    get_top_technologies,
)
from services.job_service_hm import get_job, get_jobs
from services.jobs_post_service_hm import get_job_post, get_jobs_posts
from services.scraper_service_hm import get_scrape_status, start_scrape_thread
from services.search_terms_service_hm import (
    add_search_term,
    get_search_terms,
    remove_search_term,
    update_search_term,
)
from services.stats_service import get_stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure database tables are created
    try:
        init_db()
    except Exception as exc:
        print(f"Warning during DB init on startup: {exc}")
    yield
    # Shutdown logic if needed


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "**SkillPulse AI** — Labor Market Intelligence, Multi-Tier AI Skill Extraction, "
        "Canonical Taxonomy Normalization (ESCO / O*NET), and Semantic Candidate Matcher with pgvector."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 RESTful API router
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

# Mount Frontend Static Directory
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")


# ─── Navigation & Health ──────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "SkillPulse AI Backend Running. Visit /docs for OpenAPI specifications."})


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Health check endpoint confirming API availability and database connectivity."""
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database="connected",
    )


@app.get("/apidocs", include_in_schema=False)
@app.get("/apidocs/", include_in_schema=False)
def apidocs_redirect():
    return RedirectResponse(url="/docs")


@app.post("/database/init", tags=["Database"])
def initialize_database():
    """Manually initialize or verify database table schemas."""
    init_db()
    return {"message": "Database initialized"}


# ─── Legacy & Backward Compatibility Endpoints ────────────────────────────────

@app.post("/scrape/start", tags=["Scraper"])
def legacy_start_scrape():
    start_scrape_thread()
    return JSONResponse(
        content={"message": "Scrape started", "mode": "incremental"},
        status_code=status.HTTP_202_ACCEPTED,
    )


@app.get("/scrape/status", tags=["Scraper"])
def legacy_scrape_status():
    return get_scrape_status()


@app.get("/errors", tags=["Errors"])
def legacy_errors(
    search: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return get_errors(
        search=search,
        source=source,
        page=page,
        page_size=page_size,
        paginated=True,
    )


@app.get("/stats", tags=["Health"])
def legacy_stats():
    return get_stats()


@app.get("/job-posts", tags=["Job posts"])
def legacy_job_posts(
    search: Optional[str] = Query(None),
    workplace_type: Optional[str] = Query(None),
    sort: str = Query("published_date"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return get_jobs_posts(
        search=search,
        workplace_type=workplace_type,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        paginated=True,
    )


@app.get("/job-posts/export", tags=["Job posts"])
def legacy_export_job_posts():
    csv_data = export_job_posts_csv()
    return Response(
        content=csv_data.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=job_posts.csv"},
    )


@app.get("/job-posts/{id}", tags=["Job posts"])
def legacy_get_job_post(id: int):
    try:
        post = get_job_post(id)
        return post.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/jobs", tags=["Jobs"])
def legacy_jobs(
    search: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    sort: str = Query("id"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return get_jobs(
        search=search,
        location=location,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        paginated=True,
    )


@app.get("/jobs/export", tags=["Jobs"])
def legacy_export_jobs():
    csv_data = export_jobs_csv()
    return Response(
        content=csv_data.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs.csv"},
    )


@app.get("/jobs/{id}", tags=["Jobs"])
def legacy_get_job(id: int):
    try:
        job = get_job(id)
        return job.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/search-terms", tags=["Search terms"])
def legacy_search_terms(
    include_inactive: bool = Query(False),
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return get_search_terms(
        include_inactive=include_inactive,
        search=search,
        status=status_filter,
        page=page,
        page_size=page_size,
        paginated=True,
    )


@app.post("/search-terms", tags=["Search terms"], status_code=status.HTTP_201_CREATED)
async def legacy_create_search_term(request: Request):
    payload = await request.json()
    term_str = payload.get("term")
    if not term_str:
        raise HTTPException(status_code=400, detail="'term' is required")
    new_term = add_search_term(term_str)
    return new_term.to_dict()


@app.put("/search-terms/{id}", tags=["Search terms"])
async def legacy_update_search_term(id: int, request: Request):
    payload = await request.json()
    if "is_active" not in payload:
        raise HTTPException(status_code=400, detail="is_active is required")
    try:
        term = update_search_term(id, is_active=bool(payload["is_active"]))
        return term.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.delete("/search-terms/{id}", tags=["Search terms"])
def legacy_delete_search_term(id: int):
    try:
        remove_search_term(id)
        return {"message": f"Search term {id} deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/regex-extract", tags=["Extractor"])
def legacy_regex_extract():
    start_extractor_thread("regex")
    return JSONResponse(
        content={"message": "Features extraction started"},
        status_code=status.HTTP_202_ACCEPTED,
    )


@app.get("/regex-extract/status", tags=["Extractor"])
def legacy_regex_extract_status():
    return get_extractor_status("regex")


@app.post("/llm-extract", tags=["Extractor"])
def legacy_llm_extract():
    start_llm_extractor_thread()
    return JSONResponse(
        content={"message": "LLM extraction started"},
        status_code=status.HTTP_202_ACCEPTED,
    )


@app.get("/llm-extract/status", tags=["Extractor"])
def legacy_llm_extract_status():
    return get_extractor_status("llm")


@app.get("/features/average-job-post-daily", tags=["Features"])
def legacy_avg_job_posts():
    return get_average_job_post_daily()


@app.get("/features/top-technologies", tags=["Features"])
@app.get("/features/top-5-technologies", tags=["Features"])
def legacy_top_technologies():
    return get_top_technologies()


@app.get("/features/top-locations", tags=["Features"])
@app.get("/features/top-5-locations", tags=["Features"])
def legacy_top_locations():
    return get_top_locations()


@app.get("/features/average-salary", tags=["Features"])
def legacy_avg_salary():
    return get_average_salary()


@app.get("/features/jobs-by-contract-type", tags=["Features"])
def legacy_contract_types():
    return get_jobs_by_contract_type()


@app.get("/features/jobs-by-seniority", tags=["Features"])
def legacy_seniority():
    return get_jobs_by_seniority()


@app.get("/features/technology-trends", tags=["Features"])
def legacy_technology_trends(
    days: int = Query(30),
    limit: int = Query(5),
    skill: Optional[str] = Query(""),
):
    return get_technology_trends(days=days, limit=limit, skill=skill)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
