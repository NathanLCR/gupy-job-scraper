from typing import Optional
from fastapi import APIRouter, Query
from schemas import ErrorLogListResponse
from services.error_service import get_errors

router = APIRouter(prefix="/errors", tags=["Diagnostics & Logs"])


@router.get("", response_model=ErrorLogListResponse)
def list_errors(
    search: Optional[str] = Query(None, description="Search term in error messages"),
    source: Optional[str] = Query(None, description="Filter by error source"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Retrieve paginated application error and ingestion failure logs."""
    result = get_errors(
        search=search,
        source=source,
        page=page,
        page_size=page_size,
        paginated=True,
    )
    return result
