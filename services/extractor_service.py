import re
from database import SessionLocal
from entities import (
    City,
    Company,
    ContractType,
    HardSkill,
    Job,
    JobsPost,
    NiceToHaveSkill,
    SoftSkill,
    State,
)
from features_extractors.regex_extractor import extract
from services.error_service import log_error

def get_or_create(session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if not instance:
        instance = model(**kwargs)
        session.add(instance)
        session.flush()
    return instance

def parse_salary(salary_data):
    if not salary_data:
        return None
    val = salary_data[0] if isinstance(salary_data, list) else salary_data
    cleaned = str(val).split(',')[0]
    nums = re.sub(r'[^\d]', '', cleaned)
    if nums:
        try:
            return int(nums)
        except ValueError:
            pass
    return None

def regex_extractor():
    db = SessionLocal()
    try:
        jobs_post = db.query(JobsPost).all()
        for job in jobs_post:
            try:
                existing_job = db.query(Job).filter_by(id=job.id).first()
                if existing_job:
                    continue

                features = extract(job.description or "")

                if not job.company_id:
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

                contract_obj = None
                c_types = features.get("contract_type", [])
                if c_types:
                    c_type_str = c_types[0][:100] if isinstance(c_types, list) else c_types[:100]
                    contract_obj = get_or_create(db, ContractType, name=c_type_str)

                hard_kills_list = []
                for s in (features.get("hard_skills") or []):
                    hard_kills_list.append(get_or_create(db, HardSkill, name=s[:120]))
                
                soft_skills_list = []
                for s in (features.get("soft_skills") or []):
                    soft_skills_list.append(get_or_create(db, SoftSkill, name=s[:120]))

                nice_skills_list = []
                for s in (features.get("nice_to_have") or []):
                    nice_skills_list.append(get_or_create(db, NiceToHaveSkill, name=s[:120]))

                salary_val = parse_salary(features.get("salary"))

                new_job = Job(
                    id=job.id,
                    job_title=(job.name or "Vaga sem título")[:255],
                    extractor_type="regex",
                    salary=salary_val,
                    tech_stack=features.get("tech_stack") or [],
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
                    source="regex_extractor",
                )
                print(f"Failed to process job {job.id}: {exc}")
    finally:
        db.close()