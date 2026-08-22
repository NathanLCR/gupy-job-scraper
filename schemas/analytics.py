from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SkillDemandItem(BaseModel):
    name: str
    count: int
    percentage: float = 0.0
    avg_salary: Optional[float] = None
    category: str = "hard_skill"


class SkillAnalyticsResponse(BaseModel):
    total_jobs: int = 0
    distinct_skills: int = 0
    distinct_companies: int = 0
    markets_tracked: int = 0
    top_skills: List[SkillDemandItem] = []
    top_locations: List[Dict[str, Any]] = []
    salary_by_seniority: List[Dict[str, Any]] = []
    contract_types: List[Dict[str, Any]] = []
    workplace_distribution: List[Dict[str, Any]] = []
    region: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    label: str
    category: str = "technical"
    value: int = 1  # Node weight based on occurrences
    cluster: Optional[str] = None
    esco_uri: Optional[str] = None
    onet_code: Optional[str] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int = 1  # Edge weight based on co-occurrences
    lift: Optional[float] = None
    support: Optional[float] = None


class ClusterInfo(BaseModel):
    name: str
    size: int
    skills: List[str] = []


class SkillGraphResponse(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    total_skills: int = 0
    total_connections: int = 0
    clusters: List[ClusterInfo] = []


class TaxonomyNodeResponse(BaseModel):
    id: int
    code: str
    name: str
    type: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    children: List["TaxonomyNodeResponse"] = []


class TaxonomyListResponse(BaseModel):
    categories: List[TaxonomyNodeResponse] = []
    total_nodes: int = 0


class NormalizedSkillItem(BaseModel):
    raw_skill: str
    canonical_name: str
    category: str = "technical"
    esco_uri: Optional[str] = None
    onet_code: Optional[str] = None


class SkillNormalizeRequest(BaseModel):
    skills: List[str]


class SkillNormalizeResponse(BaseModel):
    normalized: List[NormalizedSkillItem] = []


class TrendSeriesItem(BaseModel):
    name: str
    counts: List[int] = []
    total: int = 0


class TechTrendsResponse(BaseModel):
    days: int = 30
    periods: List[str] = []
    series: List[TrendSeriesItem] = []
    selected_skill: Optional[str] = None
