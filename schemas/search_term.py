from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from schemas.common import PaginationMeta


class SearchTermCreate(BaseModel):
    term: str = Field(..., min_length=1, max_length=255, description="Search keyword for job scrapers")
    is_active: bool = True


class SearchTermUpdate(BaseModel):
    is_active: bool


class SearchTermResponse(BaseModel):
    id: int
    term: str
    is_active: bool
    last_scraped_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SearchTermListResponse(BaseModel):
    items: List[SearchTermResponse] = []
    pagination: PaginationMeta
