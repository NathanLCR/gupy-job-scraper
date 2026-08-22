from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_sync_db
from entities import CandidateProfile
from schemas import (
    CandidateMatchRequest,
    CandidateMatchResponse,
    CandidateProfileCreate,
    CandidateProfileResponse,
    SkillGapExplanationRequest,
    SkillGapExplanationResponse,
)
from services.matcher_service import CandidateMatcherService
from api.v1.auth import require_admin_auth

router = APIRouter(prefix="/match", tags=["Candidate Matcher"])


@router.post("", response_model=CandidateMatchResponse)
def match_candidate_cv(
    request: CandidateMatchRequest,
    db: Session = Depends(get_sync_db),
):
    """
    Perform Candidate-to-Job matching and Skill Gap Analysis.
    Calculates weighted fit score: 50% Hard Skill Overlap + 20% Soft Skill Overlap + 30% Semantic Similarity.
    Identifies matched skills, missing critical requirements, and recommended upskilling paths.
    """
    resume_text = request.resume_text

    if not resume_text and request.profile_id:
        profile = db.get(CandidateProfile, request.profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate profile {request.profile_id} not found",
            )
        resume_text = profile.raw_resume_text

    if not resume_text or not resume_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume text or valid profile_id is required",
        )

    try:
        result = CandidateMatcherService.match_resume(
            resume_text=resume_text,
            db=db,
            target_region=request.target_region,
            seniority=request.seniority,
            limit=request.limit,
            min_fit_score=request.min_fit_score,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/explain",
    response_model=SkillGapExplanationResponse,
    dependencies=[Depends(require_admin_auth)],
)
def explain_candidate_match(
    request: SkillGapExplanationRequest,
    db: Session = Depends(get_sync_db),
):
    """
    Generate an actionable AI narrative explanation for why a candidate received their fit score
    against a specific job posting, detailing strengths, gaps, and upskilling advice.
    """
    resume_text = request.resume_text

    if not resume_text and request.profile_id:
        profile = db.get(CandidateProfile, request.profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate profile {request.profile_id} not found",
            )
        resume_text = profile.raw_resume_text

    if not resume_text or not resume_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume text or valid profile_id is required",
        )

    try:
        explanation = CandidateMatcherService.explain_fit_and_gaps(
            resume_text=resume_text,
            job_id=request.job_id,
            db=db,
        )
        return explanation
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/profile",
    response_model=CandidateProfileResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_auth)],
)
def create_candidate_profile(
    profile_in: CandidateProfileCreate,
    db: Session = Depends(get_sync_db),
):
    """Store candidate CV profile for future matching and tracking."""
    extracted = CandidateMatcherService.parse_and_extract_candidate(profile_in.raw_resume_text, db=db)
    profile = CandidateProfile(
        name=profile_in.name,
        email=profile_in.email,
        raw_resume_text=profile_in.raw_resume_text,
        parsed_skills=extracted,
        seniority=profile_in.seniority or extracted.get("seniority"),
        target_region=profile_in.target_region,
        target_role=profile_in.target_role or extracted.get("job_title"),
        years_experience=profile_in.years_experience or extracted.get("years_experience"),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile.to_dict()


@router.get(
    "/profile/{id}",
    response_model=CandidateProfileResponse,
    dependencies=[Depends(require_admin_auth)],
)
def get_candidate_profile(
    id: int,
    db: Session = Depends(get_sync_db),
):
    """Retrieve saved candidate profile by ID."""
    profile = db.get(CandidateProfile, id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate profile {id} not found",
        )
    return profile.to_dict()
