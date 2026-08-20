from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from schemas import (
    SearchTermCreate,
    SearchTermListResponse,
    SearchTermResponse,
    SearchTermUpdate,
)
from services.search_terms_service_hm import (
    add_search_term,
    get_search_terms,
    remove_search_term,
    update_search_term,
)

router = APIRouter(prefix="/search-terms", tags=["Search Terms"])


@router.get("", response_model=SearchTermListResponse)
def list_search_terms(
    include_inactive: bool = Query(False, description="Include inactive search terms"),
    search: Optional[str] = Query(None, description="Filter by term string"),
    status_filter: Optional[str] = Query(None, alias="status", description="active/inactive"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Retrieve paginated search terms configured for automated scrapers."""
    result = get_search_terms(
        include_inactive=include_inactive,
        search=search,
        status=status_filter,
        page=page,
        page_size=page_size,
        paginated=True,
    )
    return result


@router.post("", response_model=SearchTermResponse, status_code=status.HTTP_201_CREATED)
def create_search_term(term_in: SearchTermCreate):
    """Register a new job keyword to be periodically scraped."""
    try:
        new_term = add_search_term(term_in.term)
        return new_term.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/{id}", response_model=SearchTermResponse)
def toggle_search_term_active(id: int, term_update: SearchTermUpdate):
    """Update active status of a search term."""
    try:
        updated = update_search_term(id, is_active=term_update.is_active)
        return updated.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{id}")
def delete_search_term(id: int):
    """Remove a search term from scraping queue."""
    try:
        remove_search_term(id)
        return {"message": f"Search term {id} deleted successfully"}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
