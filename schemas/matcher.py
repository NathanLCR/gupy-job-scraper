from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CandidateProfileCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    raw_resume_text: str = Field(..., description="Raw text or parsed PDF text of candidate resume")
    target_region: Optional[str] = "Global"
    target_role: Optional[str] = None
    seniority: Optional[str] = None
    years_experience: Optional[int] = None


class CandidateProfileResponse(BaseModel):
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    raw_resume_text: str
    parsed_skills: Dict[str, Any] = {}
    seniority: Optional[str] = None
    target_region: Optional[str] = None
    target_role: Optional[str] = None
    years_experience: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateMatchRequest(BaseModel):
    resume_text: Optional[str] = Field(default=None, description="Direct resume text to match")
    profile_id: Optional[int] = Field(default=None, description="Existing CandidateProfile ID to match")
    target_region: Optional[str] = Field(default=None, description="Filter jobs by region (e.g. 'Europe', 'Latin America')")
    seniority: Optional[str] = Field(default=None, description="Filter jobs by seniority level")
    limit: int = Field(default=10, ge=1, le=50)
    min_fit_score: float = Field(default=0.0, ge=0.0, le=100.0)


class SkillGapAnalysis(BaseModel):
    matched_hard_skills: List[str] = []
    missing_hard_skills: List[str] = []
    matched_soft_skills: List[str] = []
    missing_soft_skills: List[str] = []
    matched_skills: List[str] = []
    missing_critical_skills: List[str] = []
    missing_nice_to_have: List[str] = []
    recommended_skills: List[str] = []


class JobMatchItem(BaseModel):
    job_id: int
    job_title: str
    company: Optional[str] = None
    location: Optional[str] = None
    region: str
    salary: Optional[int] = None
    currency: str = "BRL"
    workplace_type: Optional[str] = None
    fit_score: float = Field(..., description="Overall calculated fit percentage 0-100%")
    hard_skill_overlap: float = Field(..., description="Hard skills overlap percentage 0-100%")
    soft_skill_overlap: float = Field(..., description="Soft skills overlap percentage 0-100%")
    vector_similarity: float = Field(..., description="Semantic embedding similarity 0-100%")
    hard_points: float = Field(default=0.0, description="Points from hard skill overlap (max 50)")
    soft_points: float = Field(default=0.0, description="Points from soft skill overlap (max 20)")
    vector_points: float = Field(default=0.0, description="Points from dense vector similarity (max 30)")
    total_points: float = Field(default=0.0, description="Total composite points (max 100)")
    match_reason: Optional[str] = Field(default=None, description="Human-readable explanation of why this job matched")
    gap_analysis: SkillGapAnalysis


class CandidateMatchResponse(BaseModel):
    extracted_skills: Dict[str, List[str]]
    candidate_summary: Optional[Dict[str, Any]] = Field(default=None, description="Granular area strength and market fit summary")
    target_region: Optional[str] = None
    total_evaluated: int
    total_matches: int
    matches: List[JobMatchItem]


class SkillGapExplanationRequest(BaseModel):
    resume_text: Optional[str] = Field(default=None, description="Direct resume text or profile summary")
    profile_id: Optional[int] = Field(default=None, description="Candidate profile ID if previously saved")
    job_id: int = Field(..., description="Target Job ID to analyze and explain fit against")


class SkillGapExplanationResponse(BaseModel):
    job_id: int
    job_title: str
    company: Optional[str] = None
    fit_score: float
    hard_skill_overlap: float
    soft_skill_overlap: float
    vector_similarity: float
    matched_hard_skills: List[str] = []
    missing_hard_skills: List[str] = []
    recommended_upskilling: List[str] = []
    explanation: str = Field(..., description="Actionable narrative explanation of the fit score and specific skill gaps")


