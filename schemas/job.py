from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from schemas.common import PaginationMeta


class JobResponse(BaseModel):
    id: int
    source: str = "gupy"
    job_title: str
    extractor_type: str = "regex"
    salary: Optional[int] = None
    seniority: Optional[str] = None
    years_experience: Optional[int] = None
    tech_stack: List[str] = []
    description: Optional[str] = None
    region: str = "Latin America"
    country_code: str = "BR"
    currency: str = "BRL"
    workplace_type: Optional[str] = None
    fingerprint: Optional[str] = None
    company_id: Optional[int] = None
    contract_type_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    company: Optional[str] = None
    contract_type: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    hard_skills: List[str] = []
    soft_skills: List[str] = []
    nice_to_have_skills: List[str] = []
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    items: List[JobResponse] = []
    pagination: PaginationMeta


class JobPostResponse(BaseModel):
    id: int
    source: str = "gupy"
    company_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    career_page_id: Optional[int] = None
    career_page_name: Optional[str] = None
    career_page_logo: Optional[str] = None
    career_page_url: Optional[str] = None
    job_type: Optional[str] = None
    published_date: Optional[str] = None
    application_deadline: Optional[str] = None
    is_remote_work: Optional[bool] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    job_url: Optional[str] = None
    workplace_type: Optional[str] = None
    disabilities: Optional[bool] = None
    skills: Optional[str] = None
    badges: Optional[str] = None
    region: str = "Latin America"
    country_code: str = "BR"
    currency: str = "BRL"
    fingerprint: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobPostListResponse(BaseModel):
    items: List[JobPostResponse] = []
    pagination: PaginationMeta


class JobFilterParams(BaseModel):
    search: Optional[str] = None
    source: Optional[str] = None
    region: Optional[str] = None
    country_code: Optional[str] = None
    workplace_type: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    skill: Optional[str] = None
    sort: str = "id"
    order: str = "desc"
    page: int = 1
    page_size: int = 20


class IngestSourceInfo(BaseModel):
    id: str
    name: str
    description: str
    region: str
    country_code: str
    currency: str
    endpoint: str
    is_active: bool = True
    supports_terms: bool = True


class IngestSourcesResponse(BaseModel):
    sources: List[IngestSourceInfo] = []


class IngestStatusResponse(BaseModel):
    running: bool
    source: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    total_fetched: int = 0
    total_inserted: int = 0
    total_skipped: int = 0
    sources_stats: Dict[str, Any] = {}


class JobIngestRequest(BaseModel):
    source: str = Field(default="gupy", description="Source adapter (all, arbeitnow, remotive, jobicy, himalayas, remoteok, gupy)")
    term: Optional[str] = Field(default=None, description="Search term for ingestion")
    region: Optional[str] = Field(default="Latin America", description="Target region")
    limit: Optional[int] = Field(default=20, ge=1, le=200, description="Max jobs to fetch per source")
    auto_extract: bool = Field(default=True, description="Automatically trigger AI extraction on newly ingested jobs")
    raw_payload: Optional[List[Dict[str, Any]]] = Field(default=None, description="Direct JSON payload for direct ingestion")


class HybridSearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query or keywords")
    region: Optional[str] = Field(default=None, description="Filter by region (e.g. Europe, Latin America)")
    country_code: Optional[str] = Field(default=None, description="ISO country code (e.g. IE, BR)")
    workplace_type: Optional[str] = Field(default=None, description="REMOTE, HYBRID, ONSITE")
    seniority: Optional[str] = Field(default=None, description="Seniority level (Junior, Mid, Senior, Lead)")
    min_salary: Optional[int] = Field(default=None, description="Minimum salary threshold")
    max_salary: Optional[int] = Field(default=None, description="Maximum salary threshold")
    skill: Optional[str] = Field(default=None, description="Required skill keyword")
    location: Optional[str] = Field(default=None, description="City or State filter")
    top_k: int = Field(default=20, ge=1, le=100, description="Maximum number of results to return")
    dense_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="RRF weight for dense vector search")
    sparse_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="RRF weight for sparse full-text search")


class HybridSearchItem(BaseModel):
    job_id: int
    job: JobResponse
    rrf_score: float = Field(..., description="Reciprocal Rank Fusion score (k=60)")
    dense_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    sparse_score: float = Field(..., description="Lexical match score")
    dense_rank: int = Field(..., description="1-based rank in dense retrieval")
    sparse_rank: int = Field(..., description="1-based rank in sparse retrieval")
    normalized_score: float = Field(..., description="Normalized hybrid match score (0-100%)")


class HybridSearchResponse(BaseModel):
    query: str
    total_results: int
    items: List[HybridSearchItem] = []
