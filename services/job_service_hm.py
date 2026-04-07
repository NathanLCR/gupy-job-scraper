from services.error_service import log_error
from entities.job import Job
from sqlalchemy import Select
from database import SessionLocal

def get_jobs():
    query = Select(Job).order_by(Job.id.desc())
    return SessionLocal().scalars(query).all()

def get_job(id):
    query = Select(Job).where(Job.id==id)
    try:
        job = SessionLocal().scalars(query).first()
        if job is None:
            raise ValueError(f"Job with id {id} not found")
        return job
    except Exception as e:
        log_error(
            message=f"Error getting job with id {id}: {str(e)}",
            source="job_service_hm.get_job",
            payload=str(e),
        )