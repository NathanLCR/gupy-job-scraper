from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class PaginationMeta(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    total_items: int = Field(default=0, ge=0)
    total_pages: int = Field(default=1, ge=1)
    has_next: bool = False
    has_prev: bool = False


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "SkillPulse"
    version: str = "1.0.0"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    status: Literal["ready", "not_ready"]
    database: Literal["connected", "unavailable"]
    schema_state: Literal["current", "outdated", "unknown"] = Field(serialization_alias="schema")
    version: str = "1.0.0"
    dependencies: Dict[str, Literal["connected", "unavailable", "degraded"]]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    environment: Optional[str] = "development"
    database: str = "connected"


class StatsResponse(BaseModel):
    job_posts_count: int = 0
    jobs_count: int = 0
    companies_count: int = 0
    skills_count: int = 0
    error_logs_count: int = 0
    search_terms_count: int = 0


class ErrorLogResponse(BaseModel):
    id: int
    source: str
    message: str
    term: Optional[str] = None
    page: Optional[int] = None
    request_limit: Optional[int] = None
    payload: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ErrorLogListResponse(BaseModel):
    items: List[ErrorLogResponse] = []
    pagination: PaginationMeta


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
