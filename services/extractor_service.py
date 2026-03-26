from database import SessionLocal
from entities import Job, JobsPost
from features_extractors.regex_extractor import extract

from services.error_service import log_error


def regex_extractor():
    db = SessionLocal()
    jobs_post = db.query(JobsPost).all()
    for job in jobs_post:
        try: 
            features = extract(job.description)
            new_job = Job(
                id=job.id,
                hard_skills=features["hard_skills"],
                soft_skills=features["soft_skills"],
                nice_to_have=features["nice_to_have"],
                years_experience=features["years_experience"],
                salary=features["salary"],
                contract_type=features["contract_type"],
            )
            db.add(new_job)
            db.commit()
        except Exception as exc:
            log_error(
                f"Failed to process job {job.id}: {exc}",
                term=None,
                page=None,
                request_limit=None,
                payload=job.description,
                source="regex_extractor",
            )
            db.rollback()