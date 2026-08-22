"""
SkillPulse AI Multi-Tier Extraction Cascade & Orchestration Service.
Coordinates Tier 1 (Trie/Regex), Tier 2 (JobBERT NER), and Tier 3 (Ollama LLM)
with an intelligent confidence router (SPEC §3.2).
"""

import logging
import re
from datetime import UTC, datetime
from threading import Lock, Thread
from typing import Any, Dict, List, Optional, Union

from database import SessionLocal
from entities import (
    City,
    Company,
    ContractType,
    HardSkill,
    Job,
    JobPost,
    NiceToHaveSkill,
    SoftSkill,
    State,
)
from features_extractors.bert_extractor import extract as bert_extract
from features_extractors.llm_extractor import extract as llm_extract
from features_extractors.regex_extractor import (
    extract as regex_extract,
    normalise_skill_label,
)
from services.embedding_service import embed_job_text
from services.error_service import log_error

logger = logging.getLogger(__name__)

_extractor_lock = Lock()


def get_or_create(session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if not instance:
        instance = model(**kwargs)
        session.add(instance)
        session.flush()
    return instance


def _new_extractor_status():
    return {
        "running": False,
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


extractor_statuses = {
    "regex": _new_extractor_status(),
    "bert": _new_extractor_status(),
    "llm": _new_extractor_status(),
    "cascade": _new_extractor_status(),
}


def get_extractor_status(extractor_type="regex"):
    with _extractor_lock:
        status_dict = extractor_statuses.get(extractor_type, _new_extractor_status())
        return dict(status_dict)


def parse_salary(salary_data: Any) -> Optional[int]:
    """Parse salary to integer value if present."""
    if not salary_data:
        return None
    if isinstance(salary_data, dict):
        return salary_data.get("min") or salary_data.get("max")
    val = salary_data[0] if isinstance(salary_data, list) else salary_data
    val_str = str(val).split(",")[0].strip()
    match = re.search(r"\d+(?:\.\d+)*", val_str)
    if match:
        try:
            nums = match.group(0).replace(".", "")
            return int(nums)
        except ValueError:
            pass
    return None


def normalize_contract_type(c_type_str: Any) -> str:
    if not c_type_str:
        return "CLT"
    c_lower = str(c_type_str).lower()
    if "pj" in c_lower or "jurídica" in c_lower or "juridica" in c_lower:
        return "PJ / Pessoa Jurídica"
    if "estág" in c_lower or "estag" in c_lower or "intern" in c_lower:
        return "Estágio"
    return "CLT"


def normalize_skill_names(skills: Optional[List[str]]) -> List[str]:
    normalized = []
    seen = set()
    for skill in skills or []:
        label = normalise_skill_label(skill)[:120]
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(label)
    return normalized


# ==============================================================================
# CONFIDENCE ROUTER & CASCADE ORCHESTRATOR
# ==============================================================================

def calculate_confidence(
    tier1_res: Dict[str, Any],
    tier2_res: Optional[Dict[str, Any]] = None,
    raw_text: str = "",
) -> float:
    """
    Computes an extraction confidence score between 0.0 and 1.0 based on:
    - Number of hard skills extracted
    - Resolution of seniority and experience
    - Clarity of job context & structure
    """
    hard_skills = tier1_res.get("hard_skills") or []
    score = 0.0

    # Skill density
    num_skills = len(hard_skills)
    if num_skills >= 4:
        score += 0.50
    elif num_skills >= 2:
        score += 0.40
    elif num_skills == 1:
        score += 0.25

    # Seniority resolved
    if tier1_res.get("seniority"):
        score += 0.20

    # Experience resolved
    if tier1_res.get("years_experience") is not None:
        score += 0.15

    # Soft skills or nice-to-have detected
    if tier1_res.get("soft_skills") or tier1_res.get("nice_to_have"):
        score += 0.10

    # Tech stack resolved
    if tier1_res.get("tech_stack"):
        score += 0.05

    # Boost slightly if Tier 2 corroborated skills
    if tier2_res and tier2_res.get("hard_skills"):
        score += 0.05

    return min(1.0, round(score, 2))


def extract_cascade(
    text: str,
    tier_threshold: float = 0.85,
    force_tier: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Multi-tier extraction orchestrator.
    Runs Tier 1 (Trie/Regex) and Tier 2 (JobBERT), computes confidence,
    and selectively invokes Tier 3 (Ollama LLM) only when confidence < tier_threshold.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        return {
            "job_title": None,
            "seniority": None,
            "years_experience": None,
            "contract_type": ["CLT"],
            "salary": None,
            "hard_skills": [],
            "soft_skills": [],
            "nice_to_have": [],
            "tech_stack": [],
            "tier_used": "tier1_regex",
            "confidence": 0.0,
        }

    # Direct tier overrides
    if force_tier in ("regex", "tier1"):
        res = regex_extract(cleaned_text)
        res["tier_used"] = "tier1_regex"
        res["confidence"] = 1.0 if res.get("hard_skills") else 0.5
        return res

    if force_tier in ("bert", "tier2"):
        res = bert_extract(cleaned_text)
        res["tier_used"] = "tier2_bert"
        res["confidence"] = res.get("confidence_score", 0.7)
        return res

    if force_tier in ("llm", "tier3"):
        res = llm_extract(cleaned_text)
        res["tier_used"] = "tier3_ollama_llm"
        res["confidence"] = res.get("confidence_score", 0.9)
        return res

    # 1. Execute Tier 1 (High-speed exact matching)
    t1_result = regex_extract(cleaned_text)

    # 2. Execute Tier 2 (Contextual NER for emerging skills)
    t2_result = bert_extract(cleaned_text)

    # Merge Tier 1 + Tier 2 skills
    combined_hard = list(t1_result.get("hard_skills", []))
    for s in t2_result.get("hard_skills", []):
        norm = normalise_skill_label(s)
        if norm not in combined_hard:
            combined_hard.append(norm)

    t1_result["hard_skills"] = sorted(list(set(combined_hard)))

    # Compute cascade confidence score
    confidence = calculate_confidence(t1_result, t2_result, raw_text=cleaned_text)

    # Decision boundary: Bypass Tier 3 if confidence >= tier_threshold
    if confidence >= tier_threshold:
        t1_result["tier_used"] = "tier1_regex"
        t1_result["confidence"] = confidence
        return t1_result

    # 3. Low confidence or ambiguous: Trigger Tier 3 (Cloud AI Router)
    logger.info(f"Confidence {confidence} < {tier_threshold}. Routing to Tier 3 (Cloud AI Router)...")
    t3_result = llm_extract(cleaned_text)

    # Merge Tier 3 enriched intelligence
    final_hard = set(t1_result.get("hard_skills", [])) | set(t3_result.get("hard_skills", []))
    final_soft = set(t1_result.get("soft_skills", [])) | set(t3_result.get("soft_skills", []))
    final_nice = set(t1_result.get("nice_to_have", [])) | set(t3_result.get("nice_to_have", []))
    final_stacks = set(t1_result.get("tech_stack", [])) | set(t3_result.get("tech_stack", []))

    seniority = t1_result.get("seniority") or t3_result.get("seniority")
    years_exp = t1_result.get("years_experience") if t1_result.get("years_experience") is not None else t3_result.get("years_experience")
    salary = t3_result.get("salary") or t1_result.get("salary")
    contract = t3_result.get("contract_type") or t1_result.get("contract_type") or ["CLT"]

    tier_used_tag = t3_result.get("tier_used") or "tier3_cloud_llm"

    return {
        "job_title": t3_result.get("job_title") or t1_result.get("job_title"),
        "seniority": seniority,
        "years_experience": years_exp,
        "contract_type": contract,
        "salary": salary,
        "hard_skills": normalize_skill_names(list(final_hard)),
        "soft_skills": sorted(list(final_soft)),
        "nice_to_have": normalize_skill_names(list(final_nice)),
        "tech_stack": sorted(list(final_stacks)),
        "tier_used": tier_used_tag,
        "confidence": max(confidence, t3_result.get("confidence_score", 0.85)),
    }


# ==============================================================================
# BATCH WORKER INTEGRATION (Chunked Slicer & Rate-Limit Backoff)
# ==============================================================================

def _run_extractor(extractor_type, extractor_fn, *, error_source, limit=None):
    import time
    from config import settings

    with _extractor_lock:
        status = extractor_statuses[extractor_type]
        if status["running"]:
            return
        status["running"] = True
        status["started_at"] = datetime.now(UTC).isoformat()
        status["finished_at"] = None
        status["error"] = None

    db = SessionLocal()
    try:
        query = (
            db.query(JobPost)
            .outerjoin(Job, JobPost.id == Job.id)
            .filter(Job.id == None)
        )
        if limit is not None:
            query = query.limit(limit)

        jobs_to_extract = query.all()
        total_items = len(jobs_to_extract)
        batch_size = getattr(settings, "EXTRACTION_BATCH_SIZE", 15)
        delay = getattr(settings, "EXTRACTION_RATE_LIMIT_DELAY", 2.0)

        # Process in chunked batches
        for i in range(0, total_items, batch_size):
            batch = jobs_to_extract[i : i + batch_size]
            for job in batch:
                try:
                    features = extractor_fn(job.description or "")
                    if not features:
                        continue

                    c_name = (job.career_page_name or (f"Empresa {job.company_id}" if job.company_id else "Empresa Confidencial"))[:255]
                    company = None
                    if job.company_id:
                        company = db.query(Company).filter_by(id=job.company_id).first()
                    if not company:
                        company = db.query(Company).filter_by(name=c_name).first()
                    if not company:
                        company = Company(id=job.company_id if job.company_id else None, name=c_name)
                        db.add(company)
                        db.flush()

                    state_name = job.state or job.country or job.region or "Global"
                    state_obj = get_or_create(db, State, name=state_name[:100])
                    city_obj = None

                    if job.city:
                        city_obj = get_or_create(db, City, name=job.city[:150], state_id=state_obj.id if state_obj else None)

                    c_types = features.get("contract_type", [])
                    raw_c_type = c_types[0] if isinstance(c_types, list) and c_types else ("CLT" if not c_types else str(c_types))
                    normalized_c_type = normalize_contract_type(raw_c_type)
                    contract_obj = get_or_create(db, ContractType, name=normalized_c_type)

                    hard_skills_list = []
                    for s in normalize_skill_names(features.get("hard_skills") or []):
                        hard_skills_list.append(get_or_create(db, HardSkill, name=s[:120]))

                    soft_skills_list = []
                    for s in normalize_skill_names(features.get("soft_skills") or []):
                        soft_skills_list.append(get_or_create(db, SoftSkill, name=s[:120]))

                    nice_skills_list = []
                    for s in normalize_skill_names(features.get("nice_to_have") or []):
                        nice_skills_list.append(get_or_create(db, NiceToHaveSkill, name=s[:120]))

                    salary_val = parse_salary(features.get("salary"))
                    tech_stack_items = normalize_skill_names(features.get("tech_stack") or features.get("hard_skills") or [])
                    resolved_title = (features.get("job_title") or job.name or "Vaga sem título")[:255]

                    # Generate 384-dimensional dense vector embedding
                    embedding_vec = embed_job_text(
                        job_title=resolved_title,
                        tech_stack=tech_stack_items,
                        hard_skills=[s.name for s in hard_skills_list],
                        description=job.description,
                        seniority=features.get("seniority"),
                    )

                    new_job = Job(
                        id=job.id,
                        source=getattr(job, "source", "gupy") or "gupy",
                        job_title=resolved_title,
                        extractor_type=features.get("tier_used") or extractor_type,
                        salary=salary_val,
                        seniority=features.get("seniority"),
                        years_experience=features.get("years_experience"),
                        tech_stack=tech_stack_items,
                        description=job.description,
                        region=getattr(job, "region", "Latin America") or "Latin America",
                        country_code=getattr(job, "country_code", "BR") or "BR",
                        currency=getattr(job, "currency", "BRL") or "BRL",
                        workplace_type=getattr(job, "workplace_type", None) or ("REMOTE" if job.is_remote_work else "ONSITE"),
                        fingerprint=getattr(job, "fingerprint", None),
                        embedding=embedding_vec,
                        company_id=company.id,
                        contract_type_id=contract_obj.id if contract_obj else None,
                        state_id=state_obj.id if state_obj else None,
                        city_id=city_obj.id if city_obj else None,
                        hard_skills=hard_skills_list,
                        soft_skills=soft_skills_list,
                        nice_to_have_skills=nice_skills_list,
                    )

                    db.add(new_job)
                    db.commit()

                    # Throttle only when external Cloud LLM (Tier 3) is actually invoked
                    if extractor_type == "llm" or (features and "tier3" in str(features.get("tier_used", ""))):
                        time.sleep(delay)

                except Exception as exc:
                    db.rollback()
                    log_error(
                        f"Failed to process job {job.id}: {exc}",
                        term=None,
                        page=None,
                        request_limit=None,
                        payload=job.description,
                        source=error_source,
                    )
                    logger.error(f"Failed to process job {job.id}: {exc}")

    except Exception as general_exc:
        with _extractor_lock:
            extractor_statuses[extractor_type]["error"] = str(general_exc)
    finally:
        with _extractor_lock:
            extractor_statuses[extractor_type]["running"] = False
            extractor_statuses[extractor_type]["finished_at"] = datetime.now(UTC).isoformat()
        db.close()


def regex_extractor():
    _run_extractor("regex", regex_extract, error_source="regex_extractor")


def llm_extractor(limit=None):
    _run_extractor("llm", llm_extract, error_source="llm_extractor", limit=limit)


def cascade_extractor(limit=None):
    _run_extractor("cascade", extract_cascade, error_source="cascade_extractor", limit=limit)


def start_extractor_thread(extractor_type="regex", *, limit=None):
    if extractor_type == "llm":
        target = lambda: llm_extractor(limit=limit)
    elif extractor_type == "cascade":
        target = lambda: cascade_extractor(limit=limit)
    else:
        target = regex_extractor

    thread = Thread(target=target)
    thread.daemon = True
    thread.start()


def start_llm_extractor_thread(*, limit=None):
    start_extractor_thread("llm", limit=limit)
