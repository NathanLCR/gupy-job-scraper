from fastapi import APIRouter, Depends

from api.v1.analytics import router as analytics_router
from api.v1.auth import require_admin_auth, router as auth_router
from api.v1.errors import router as errors_router
from api.v1.extract import router as extract_router
from api.v1.jobs import router as jobs_router
from api.v1.match import router as match_router
from api.v1.search_terms import router as search_terms_router
from api.v1.stats import router as stats_router
from api.v1.tasks import router as tasks_router

api_v1_router = APIRouter()

# Public Candidate Intelligence & Exploration Endpoints
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(extract_router)
api_v1_router.include_router(match_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(auth_router)

# Operator & Pipeline Endpoints (Protected by Admin Auth)
api_v1_router.include_router(tasks_router, dependencies=[Depends(require_admin_auth)])
api_v1_router.include_router(search_terms_router, dependencies=[Depends(require_admin_auth)])
api_v1_router.include_router(errors_router, dependencies=[Depends(require_admin_auth)])
api_v1_router.include_router(stats_router)

