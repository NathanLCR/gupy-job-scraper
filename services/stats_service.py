from sqlalchemy import select, func
from database import SessionLocal
from entities import JobPost, Job, SearchTerm, ErrorLog, Company, HardSkill


def get_stats():
    db = SessionLocal()
    try:
        job_posts_count = db.scalar(select(func.count(JobPost.id))) or 0
        jobs_count = db.scalar(select(func.count(Job.id))) or 0
        companies_count = db.scalar(select(func.count(Company.id))) or 0
        skills_count = db.scalar(select(func.count(HardSkill.id))) or 0
        terms_count = db.scalar(select(func.count(SearchTerm.id))) or 0
        errors_count = db.scalar(select(func.count(ErrorLog.id))) or 0
        return {
            "job_posts_count": job_posts_count,
            "jobs_count": jobs_count,
            "companies_count": companies_count,
            "skills_count": skills_count,
            "search_terms_count": terms_count,
            "error_logs_count": errors_count,
            "total_jobs": job_posts_count,
            "total_processed": jobs_count,
            "total_terms": terms_count,
            "total_errors": errors_count,
        }
    finally:
        db.close()