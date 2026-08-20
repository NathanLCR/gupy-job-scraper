from fastapi import APIRouter
from schemas import StatsResponse
from services.stats_service import get_stats

router = APIRouter(prefix="/stats", tags=["Diagnostics & Logs"])


@router.get("", response_model=StatsResponse)
def get_system_stats():
    """Retrieve high-level system entity counts and database metrics."""
    return get_stats()
