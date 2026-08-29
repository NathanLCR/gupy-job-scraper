from contextlib import asynccontextmanager
import logging
import os
import time
import uuid
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.v1.auth import audit_operator_event, require_admin_auth
from api.v1.router import api_v1_router
from config import settings
from database import SessionLocal
from schemas import LivenessResponse, ReadinessResponse
from services.postgres_retrieval_service import evaluate_retrieval_activation
from services.readiness_service import check_database_readiness, check_redis_readiness
from services.csv_service import export_job_posts_csv
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
    settings.validate_runtime_config()
    settings.validate_runtime_dependencies()

    # Fail-fast database readiness check
    result = check_database_readiness()
    if settings.ENVIRONMENT.lower() == "production" and not result.ready:
        raise RuntimeError(f"Startup readiness failed: {result.failure_category}")

    if (
        settings.ENVIRONMENT.lower() == "production"
        and settings.POSTGRES_INDEXED_RETRIEVAL_ENABLED
    ):
        with SessionLocal() as db:
            activation = evaluate_retrieval_activation(db)
        if not activation.can_activate:
            raise RuntimeError("Indexed retrieval activation failed")

    app.state.startup_readiness = result
    yield
    # Shutdown logic if needed


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "**SkillPulse** — Labor Market Intelligence, Canonical Taxonomy Normalization (ESCO / O*NET), "
        "and Explainable Semantic Candidate Matcher with PostgreSQL and pgvector."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

api_error_logger = logging.getLogger("skillpulse.api_errors")


@app.exception_handler(Exception)
async def unexpected_api_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a stable, cache-resistant error without exposing exception details."""
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    request.state.request_id = request_id
    api_error_logger.error(
        "unexpected_api_failure",
        extra={
            "event": "unexpected_api_failure",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error.", "request_id": request_id},
        headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
    )

# CORS Middleware Configuration
def _get_cors_origins():
    try:
        return list(settings.get_cors_origins())
    except RuntimeError:
        if settings.ENVIRONMENT.lower() == "production":
            raise
        return ["http://localhost:8000", "http://127.0.0.1:8000"]


class _ScopedCORSMiddleware:
    """
    Applies a stricter CORS policy to the operator authentication surface
    (`/api/v1/admin/*`) than to public read endpoints (Spec 08 §7).

    Starlette's `CORSMiddleware` is a single, application-wide policy; the
    public policy below intentionally allows any `*.pages.dev` preview
    subdomain so the deployed frontend keeps working across preview
    deploys. That regex must never extend to `/api/v1/admin/*` — it is the
    surface that manages and reveals session-cookie authentication state
    (`/login`, `/logout`, `/verify`), and a cross-origin reader there is
    exactly the "operator routes allow only the operator origin" case this
    specification forbids. This wraps the same inner app with two
    independent `CORSMiddleware` instances and dispatches by path, so the
    admin policy is enforced regardless of what the public policy allows.
    """

    def __init__(self, app, *, admin_path_prefix: str, public_kwargs: dict, admin_kwargs: dict):
        self._admin_path_prefix = admin_path_prefix
        self._public = CORSMiddleware(app, **public_kwargs)
        self._admin = CORSMiddleware(app, **admin_kwargs)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith(self._admin_path_prefix):
            await self._admin(scope, receive, send)
        else:
            await self._public(scope, receive, send)


cors_origins = _get_cors_origins()
app.add_middleware(
    _ScopedCORSMiddleware,
    admin_path_prefix=f"{settings.API_V1_PREFIX}/admin",
    public_kwargs=dict(
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.pages\.dev",
        allow_methods=["*"],
        allow_headers=["*"],
    ),
    admin_kwargs=dict(
        # No cross-origin caller is ever legitimate for the operator
        # session surface: the console and its API share one origin
        # (Spec 08 §3.1), so no origin is allow-listed here at all. A
        # same-origin request from the console itself is never subject to
        # CORS in the first place, so this has no effect on it; a
        # cross-origin request — from any origin, including the ones the
        # public policy above allows — gets no `Access-Control-Allow-Origin`
        # and fails preflight for state-changing requests.
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    ),
)

# ─── Public & Quota Rate Limiting Middleware (Distributed Redis Limiter) ──────
from services.rate_limit_policy import resolve_rate_limit_policy
from services.client_identity_service import resolve_client_identity, digest_client_identity, short_digest
from services.rate_limit_service import get_rate_limiter, RateLimitUnavailableError

logger = logging.getLogger("skillpulse.rate_limit")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Protects public endpoints and quota-bound AI services across all workers
    using distributed Redis sliding windows and spoof-resistant client identity.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)

    policy = resolve_rate_limit_policy(request.method, request.url.path)
    if policy is None:
        return await call_next(request)

    trusted_networks = settings.get_trusted_proxy_networks()
    identity = resolve_client_identity(
        request,
        trusted_networks=trusted_networks,
        trust_cloudflare=settings.TRUST_CLOUDFLARE_CONNECTING_IP,
    )
    salt = settings.RATE_LIMIT_KEY_SALT or "default-development-salt-at-least-32-chars-long"
    subject = digest_client_identity(identity.normalized_ip, salt)

    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or uuid.uuid4().hex

    try:
        limiter = get_rate_limiter()
        start_time = time.perf_counter()
        decision = limiter.check(policy.scope, subject, policy.limit, policy.window_seconds)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    except RateLimitUnavailableError:
        if settings.RATE_LIMIT_SHADOW:
            logger.warning(
                "Rate limit store unavailable (shadow mode, proceeding)",
                extra={
                    "event": "rate_limit_store_unavailable",
                    "scope": policy.scope,
                    "shadow": True,
                    "request_id": request_id,
                },
            )
            return await call_next(request)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Rate limit service temporarily unavailable. Please try again shortly.",
                "request_id": request_id,
            },
            headers={
                "Cache-Control": "no-store",
                "X-Request-ID": request_id,
            },
        )

    if decision.allowed:
        logger.info(
            "Rate limit allowed",
            extra={
                "event": "rate_limit_allowed",
                "scope": policy.scope,
                "subject_prefix": short_digest(subject),
                "duration_ms": duration_ms,
                "shadow": settings.RATE_LIMIT_SHADOW,
                "request_id": request_id,
            },
        )
        response = await call_next(request)
        response.headers["RateLimit-Limit"] = str(decision.limit)
        response.headers["RateLimit-Remaining"] = str(decision.remaining)
        response.headers["RateLimit-Reset"] = str(decision.reset_after_seconds)
        return response
    else:
        logger.warning(
            "Rate limit rejected",
            extra={
                "event": "rate_limit_rejected",
                "scope": policy.scope,
                "subject_prefix": short_digest(subject),
                "duration_ms": duration_ms,
                "shadow": settings.RATE_LIMIT_SHADOW,
                "request_id": request_id,
            },
        )
        if settings.RATE_LIMIT_SHADOW:
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded. Please try again later.",
                "retry_after_seconds": decision.retry_after_seconds,
                "request_id": request_id,
            },
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                "Cache-Control": "no-store",
                "RateLimit-Limit": str(decision.limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(decision.reset_after_seconds),
                "X-Request-ID": request_id,
            },
        )


@app.middleware("http")
async def operator_audit_and_security_headers(request: Request, call_next):
    """Attach baseline response protections and audit authenticated mutations."""
    request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Request-ID"] = request.state.request_id

    actor = getattr(request.state, "operator_actor_id", None)
    if actor and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        audit_operator_event(
            "operator_mutation",
            request,
            result=str(response.status_code),
            actor=actor,
            action=f"{request.method} {request.url.path}",
        )
    return response


# Include v1 RESTful API router
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

# Mount Frontend Static Directory
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")


# ─── Navigation & Static Frontend Serving ─────────────────────────────────────

@app.get("/", include_in_schema=False)
@app.get("/match", include_in_schema=False)
@app.get("/jobs", include_in_schema=False)
@app.get("/market", include_in_schema=False)
@app.get("/how-it-works", include_in_schema=False)
@app.get("/about", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def public_app():
    """Serves the public single-page application."""
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "SkillPulse AI Running. Visit /docs for OpenAPI specifications."})


# Operator console assets live outside `frontend/` on purpose: `frontend/`
# is mounted below as a public StaticFiles directory, and any file placed
# inside it is reachable unauthenticated through that mount regardless of
# what auth this route enforces (Spec 08 §3.1). Keeping admin.html/js/css
# in their own directory means there is no path — obscured or not — under
# which they can be served without going through the routes below.
operator_dir = os.path.join(os.path.dirname(__file__), "operator")
_OPERATOR_ASSET_TYPES = {
    "admin.js": "application/javascript; charset=utf-8",
    "admin.css": "text/css; charset=utf-8",
}


@app.get("/operator/login", include_in_schema=False)
def operator_login_document():
    """Serve the login-only operator entry document."""
    login_file = os.path.join(operator_dir, "login.html")
    if os.path.exists(login_file):
        return FileResponse(
            login_file,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "script-src 'unsafe-inline'; connect-src 'self'; "
                    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
                ),
            },
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@app.get(
    "/operator",
    include_in_schema=False,
    dependencies=[Depends(require_admin_auth)],
)
def operator_console():
    """Serve the operator workspace only after server-side authorization."""
    admin_file = os.path.join(operator_dir, "admin.html")
    if os.path.exists(admin_file):
        return FileResponse(
            admin_file,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "frame-ancestors 'none'",
            },
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@app.get(
    "/operator/assets/{filename}",
    include_in_schema=False,
    dependencies=[Depends(require_admin_auth)],
)
def operator_console_assets(filename: str):
    """Serve only known operator JS/CSS filenames after authorization."""
    media_type = _OPERATOR_ASSET_TYPES.get(filename)
    if not media_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    asset_file = os.path.join(operator_dir, filename)
    if not os.path.exists(asset_file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    return FileResponse(
        asset_file,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _readiness_response() -> JSONResponse:
    result = check_database_readiness()
    redis_state = check_redis_readiness()
    status_code = 200 if result.ready else 503
    payload = {
        "status": "ready" if result.ready else "not_ready",
        "database": result.database,
        "schema": result.schema_state,
        "version": settings.VERSION,
        "dependencies": {
            "database": result.database,
            "redis": redis_state.status,
        },
    }
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/health/live",
    response_model=LivenessResponse,
    tags=["Health"],
    responses={200: {"model": LivenessResponse}},
)
def liveness_check():
    """Liveness probe confirming the ASGI process can accept requests."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "SkillPulse",
            "version": settings.VERSION,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/health/ready",
    response_model=ReadinessResponse,
    tags=["Health"],
    responses={
        200: {"model": ReadinessResponse},
        503: {"model": ReadinessResponse},
    },
)
def readiness_check():
    """Readiness probe verifying database connectivity and current migration schema."""
    return _readiness_response()


@app.get(
    "/health",
    response_model=ReadinessResponse,
    tags=["Health"],
    responses={
        200: {"model": ReadinessResponse},
        503: {"model": ReadinessResponse},
    },
)
def health_check():
    """Compatibility alias for /health/ready."""
    return _readiness_response()


@app.get("/apidocs", include_in_schema=False)
@app.get("/apidocs/", include_in_schema=False)
def apidocs_redirect():
    return RedirectResponse(url="/docs")


# ─── Legacy & Backward Compatibility Endpoints (Protected) ────────────────────

@app.post("/scrape/start", tags=["Scraper"], dependencies=[Depends(require_admin_auth)])
def legacy_start_scrape():
    start_scrape_thread()
    return JSONResponse(
        content={"message": "Scrape started", "mode": "incremental"},
        status_code=status.HTTP_202_ACCEPTED,
    )


@app.get("/scrape/status", tags=["Scraper"], dependencies=[Depends(require_admin_auth)])
def legacy_scrape_status():
    return get_scrape_status()


@app.get("/errors", tags=["Errors"], dependencies=[Depends(require_admin_auth)])
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


@app.get("/stats", tags=["Health"], dependencies=[Depends(require_admin_auth)])
def legacy_stats():
    return get_stats()


@app.get("/job-posts", tags=["Job posts"], dependencies=[Depends(require_admin_auth)])
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


@app.get("/job-posts/export", tags=["Job posts"], dependencies=[Depends(require_admin_auth)])
def legacy_export_job_posts():
    csv_data = export_job_posts_csv()
    return Response(
        content=csv_data.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=job_posts.csv"},
    )


@app.get("/job-posts/{id}", tags=["Job posts"], dependencies=[Depends(require_admin_auth)])
def legacy_get_job_post(id: int):
    try:
        post = get_job_post(id)
        return post.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/search-terms", tags=["Search terms"], dependencies=[Depends(require_admin_auth)])
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


@app.post("/search-terms", tags=["Search terms"], status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_auth)])
async def legacy_create_search_term(request: Request):
    payload = await request.json()
    term_str = payload.get("term")
    if not term_str:
        raise HTTPException(status_code=400, detail="'term' is required")
    new_term = add_search_term(term_str)
    return new_term.to_dict()


@app.put("/search-terms/{id}", tags=["Search terms"], dependencies=[Depends(require_admin_auth)])
async def legacy_update_search_term(id: int, request: Request):
    payload = await request.json()
    if "is_active" not in payload:
        raise HTTPException(status_code=400, detail="is_active is required")
    try:
        term = update_search_term(id, is_active=bool(payload["is_active"]))
        return term.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.delete("/search-terms/{id}", tags=["Search terms"], dependencies=[Depends(require_admin_auth)])
def legacy_delete_search_term(id: int):
    try:
        remove_search_term(id)
        return {"message": f"Search term {id} deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/regex-extract", tags=["Extractor"], dependencies=[Depends(require_admin_auth)])
def legacy_regex_extract():
    start_extractor_thread("regex")
    return JSONResponse(
        content={"message": "Features extraction started"},
        status_code=status.HTTP_202_ACCEPTED,
    )


@app.get("/regex-extract/status", tags=["Extractor"], dependencies=[Depends(require_admin_auth)])
def legacy_regex_extract_status():
    return get_extractor_status("regex")


@app.post("/llm-extract", tags=["Extractor"], dependencies=[Depends(require_admin_auth)])
def legacy_llm_extract():
    start_llm_extractor_thread()
    return JSONResponse(
        content={"message": "LLM extraction started"},
        status_code=status.HTTP_202_ACCEPTED,
    )


@app.get("/llm-extract/status", tags=["Extractor"], dependencies=[Depends(require_admin_auth)])
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
