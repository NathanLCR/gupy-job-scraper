from sqlalchemy import Select
from entities.job_post import JobPost
from services.error_service import log_error
from database import SessionLocal
from sqlalchemy import select
import json
from utils import parse_datetime, parse_date

def save_new_job_post(jobs, last_scraped_at=None):
    db = SessionLocal()
    inserted = 0
    try:
        for job_post in jobs:
            job_post_obj = create_job_post(job_post)

            if last_scraped_at and job_post_obj.published_date and job_post_obj.published_date <= last_scraped_at.replace(tzinfo=None):
                db.commit()
                return inserted

            existing_job = db.get(JobPost, job_post['id'])
            if existing_job:
                continue

            db.add(job_post_obj)
            inserted += 1
            db.commit()
    except Exception as exc:
        log_error(
            source = "jobs_post_service_hm.save_all",
            message = "Error saving jobs",
            payload = str(exc),
        )
    finally:
        db.close()
    return inserted

def create_job_post(jobs_raw):
    return JobPost(
        id=jobs_raw['id'],
        company_id=jobs_raw['companyId'],
        name=jobs_raw['name'],
        description=jobs_raw['description'],
        career_page_id=jobs_raw['careerPageId'],
        career_page_name=jobs_raw['careerPageName'],
        career_page_logo=jobs_raw['careerPageLogo'],
        career_page_url=jobs_raw['careerPageUrl'],
        job_type=jobs_raw.get('type'),
        published_date=parse_datetime(jobs_raw.get("publishedDate")),
        application_deadline=parse_date(jobs_raw.get("applicationDeadline")),
        is_remote_work=jobs_raw.get('isRemoteWork'),
        city=jobs_raw.get('city'),
        state=jobs_raw.get('state'),
        country=jobs_raw.get('country'),
        job_url=jobs_raw.get('jobUrl'),
        workplace_type=jobs_raw.get('workplaceType'),
        disabilities=jobs_raw.get('disabilities'),
        skills=json.dumps(jobs_raw.get("skills"), ensure_ascii=False) if jobs_raw.get("skills") else None,
        badges=json.dumps(jobs_raw.get("badges"), ensure_ascii=False) if jobs_raw.get("badges") else None
    )

def get_jobs_posts():
    db = SessionLocal()
    try:
        query = Select(JobPost).order_by(JobPost.published_date.desc())
        return db.scalars(query).all()
    except Exception as e:
        log_error(
            source = "jobs_post_service_hm.get_jobs_posts",
            message = "Error getting jobs",
            payload = str(e),
        )
    finally:
        db.close()

def get_job_post(id):
    db = SessionLocal()
    query = Select(JobPost).where(JobPost.id==id)
    try:
        job_post = db.scalars(query).first()
        if job_post is None:
            raise ValueError(f"Job post with id {id} not found")
        return job_post
    except Exception as e:
        log_error(
            source = "jobs_post_service_hm.get_job_post",
            message = "Error getting job post",
            payload = str(e),
        )
        raise
    finally:
        db.close()