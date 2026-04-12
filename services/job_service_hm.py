from services.error_service import log_error
from entities.job import Job
from sqlalchemy import Select
from database import SessionLocal

def get_jobs():
    db = SessionLocal()
    query = Select(Job).order_by(Job.id.desc())
    jobs = db.scalars(query).all()
    db.close()
    return jobs

def get_job(id):
    db = SessionLocal()
    query = Select(Job).where(Job.id==id)
    try:
        job = db.scalars(query).first()
        if job is None:
            raise ValueError(f"Job with id {id} not found")
        return job
    except Exception as e:
        log_error(
            message=f"Error getting job with id {id}: {str(e)}",
            source="job_service_hm.get_job",
            payload=str(e),
        )
        raise
    finally:
        db.close()