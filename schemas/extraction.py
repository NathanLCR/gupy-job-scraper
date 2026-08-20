from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExtractionRequest(BaseModel):
    text: str = Field(..., description="Job posting or resume text to extract features from")
    extractor_type: str = Field(default="regex", description="Extractor engine: 'regex', 'llm', or 'cascade'")
    tier_threshold: float = Field(default=0.85, description="Confidence threshold to bypass higher tiers")


class SalaryInfo(BaseModel):
    raw: Optional[str] = None
    min: Optional[int] = None
    max: Optional[int] = None
    currency: Optional[str] = "BRL"


class ExtractionResponse(BaseModel):
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    years_experience: Optional[int] = None
    contract_type: List[str] = []
    salary: Optional[Any] = None
    hard_skills: List[str] = []
    soft_skills: List[str] = []
    nice_to_have: List[str] = []
    tech_stack: List[str] = []
    tier_used: str = "tier1_regex"
    confidence: float = 1.0
