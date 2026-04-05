from sqlalchemy import select, func
from database import SessionLocal
from entities import JobPost, Job, SearchTerm, ErrorLog


def get_stats():
    db = SessionLocal()
    jobs_count = db.scalar(select(func.count(JobPost.id))) or 0
    processed_jobs_count = db.scalar(select(func.count(Job.id))) or 0
    terms_count = db.scalar(select(func.count(SearchTerm.id))) or 0
    errors_count = db.scalar(select(func.count(ErrorLog.id))) or 0
    return {
        "total_jobs": jobs_count,
        "total_processed": processed_jobs_count,
        "total_terms": terms_count,
        "total_errors": errors_count
    }