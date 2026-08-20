from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from schemas import ExtractionRequest, ExtractionResponse
from services.extractor_service import (
    extract_cascade,
    get_extractor_status,
    start_extractor_thread,
    start_llm_extractor_thread,
)

router = APIRouter(prefix="/extract", tags=["Feature Extraction"])


@router.post("", response_model=ExtractionResponse)
def extract_text_features(request: ExtractionRequest):
    """
    Synchronous on-demand multi-tier skill & entity extraction on arbitrary text.
    Extracts hard skills, soft skills, nice-to-haves, seniority, years of experience, and tech stacks.
    Supports 'cascade' (default multi-tier router), 'regex' (Tier 1 fast trie), and 'llm' (Tier 3 Ollama).
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text payload cannot be empty",
        )

    extractor_type = request.extractor_type.lower()
    force_tier = extractor_type if extractor_type in ("regex", "bert", "llm") else None

    result = extract_cascade(
        text,
        tier_threshold=request.tier_threshold,
        force_tier=force_tier,
    )

    return ExtractionResponse(
        job_title=result.get("job_title"),
        seniority=result.get("seniority"),
        years_experience=result.get("years_experience"),
        contract_type=result.get("contract_type") or [],
        salary=result.get("salary"),
        hard_skills=result.get("hard_skills") or [],
        soft_skills=result.get("soft_skills") or [],
        nice_to_have=result.get("nice_to_have") or [],
        tech_stack=result.get("tech_stack") or [],
        tier_used=result.get("tier_used") or "tier1_regex",
        confidence=result.get("confidence", 1.0),
    )


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
def start_batch_extraction(
    engine: str = Query("cascade", description="Extraction engine: 'cascade', 'regex', or 'llm'"),
    limit: Optional[int] = Query(None, description="Max jobs to process in this run"),
):
    """Trigger background batch feature extraction across unprocessed raw job posts."""
    engine_clean = engine.lower()
    if engine_clean == "llm":
        start_llm_extractor_thread(limit=limit)
        return {"message": "LLM batch extraction started in background", "engine": "llm"}
    elif engine_clean == "cascade":
        start_extractor_thread("cascade", limit=limit)
        return {"message": "Cascade batch extraction started in background", "engine": "cascade"}
    else:
        start_extractor_thread("regex", limit=limit)
        return {"message": "Regex batch extraction started in background", "engine": "regex"}


@router.get("/status")
def get_batch_extraction_status(
    engine: str = Query("regex", description="Extraction engine to check ('regex', 'llm', 'cascade')"),
):
    """Retrieve extraction worker execution status and timestamps."""
    return get_extractor_status(engine)
