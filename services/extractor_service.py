import re
from datetime import datetime, UTC
from threading import Thread

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
from features_extractors.llm_extractor import extract as llm_extract
from features_extractors.regex_extractor import extract
from features_extractors.regex_extractor import normalise_skill_label
from services.error_service import log_error

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
    "llm": _new_extractor_status(),
}


def get_extractor_status(extractor_type="regex"):
    return extractor_statuses.get(extractor_type, _new_extractor_status())

def parse_salary(salary_data):
    if not salary_data:
        return None
    val = salary_data[0] if isinstance(salary_data, list) else salary_data
    val_str = str(val).split(',')[0].strip()
    match = re.search(r'\d+(?:\.\d+)*', val_str)
    if match:
        try:
            nums = match.group(0).replace('.', '')
            return int(nums)
        except ValueError:
            pass
    return None

def normalize_contract_type(c_type_str):
    if not c_type_str:
        return "CLT"
    c_lower = str(c_type_str).lower()
    if "pj" in c_lower or "jurídica" in c_lower or "juridica" in c_lower:
        return "PJ / Pessoa Jurídica"
    if "estág" in c_lower or "estag" in c_lower:
        return "Estágio"
    return "CLT"

def normalize_skill_names(skills):
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

def _run_extractor(extractor_type, extractor_fn, *, error_source, limit=None):
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

        for job in jobs_to_extract:
            try:
                features = extractor_fn(job.description or "")
                if not features:
                    continue

                company = db.query(Company).filter_by(id=job.company_id).first()

                if not company:
                    c_name = (job.career_page_name or f"Empresa {job.company_id}")[:255]
                    if db.query(Company).filter_by(name=c_name).first():
                        c_name = f"{c_name} ({job.company_id})"[:255]
                    
                    company = Company(id=job.company_id, name=c_name)
                    db.add(company)
                    db.flush()

                state_obj = None
                city_obj = None
                if job.state:
                    state_obj = get_or_create(db, State, name=job.state[:100])
                    if job.city:
                        city_obj = get_or_create(db, City, name=job.city[:150], state_id=state_obj.id)

                c_types = features.get("contract_type", [])
                raw_c_type = c_types[0] if isinstance(c_types, list) and c_types else ("CLT" if not c_types else str(c_types))
                normalized_c_type = normalize_contract_type(raw_c_type)
                contract_obj = get_or_create(db, ContractType, name=normalized_c_type)

                hard_kills_list = []
                for s in normalize_skill_names(features.get("hard_skills") or []):
                    hard_kills_list.append(get_or_create(db, HardSkill, name=s[:120]))

                soft_skills_list = []
                for s in normalize_skill_names(features.get("soft_skills") or []):
                    soft_skills_list.append(get_or_create(db, SoftSkill, name=s[:120]))

                nice_skills_list = []
                for s in normalize_skill_names(features.get("nice_to_have") or []):
                    nice_skills_list.append(get_or_create(db, NiceToHaveSkill, name=s[:120]))

                salary_val = parse_salary(features.get("salary"))

                new_job = Job(
                    id=job.id,
                    job_title=((features.get("job_title") or job.name or "Vaga sem título")[:255]),
                    extractor_type=extractor_type,
                    salary=salary_val,
                    seniority=features.get("seniority"),
                    years_experience=features.get("years_experience"),
                    tech_stack=normalize_skill_names(features.get("tech_stack") or features.get("hard_skills") or []),
                    company_id=company.id,
                    contract_type_id=contract_obj.id if contract_obj else None,
                    state_id=state_obj.id if state_obj else None,
                    city_id=city_obj.id if city_obj else None,
                    hard_skills=hard_kills_list,
                    soft_skills=soft_skills_list,
                    nice_to_have_skills=nice_skills_list,
                )

                db.add(new_job)
                db.commit()

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
                print(f"Failed to process job {job.id}: {exc}")

    except Exception as general_exc:
        status["error"] = str(general_exc)
    finally:
        status["running"] = False
        status["finished_at"] = datetime.now(UTC).isoformat()
        db.close()


def regex_extractor():
    _run_extractor("regex", extract, error_source="regex_extractor")


def llm_extractor(limit=None):
    _run_extractor("llm", llm_extract, error_source="llm_extractor", limit=limit)


def start_extractor_thread(extractor_type="regex", *, limit=None):
    target = regex_extractor
    if extractor_type == "llm":
        target = lambda: llm_extractor(limit=limit)

    thread = Thread(target=target)
    thread.daemon = True
    thread.start()


def start_llm_extractor_thread(*, limit=None):
    start_extractor_thread("llm", limit=limit)
