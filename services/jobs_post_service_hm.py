from sqlalchemy import Select, func, or_
from entities.job_post import JobPost
from services.error_service import log_error
from database import SessionLocal
from sqlalchemy import select
import json
from utils import parse_datetime, parse_date

def save_new_job_post(jobs, last_scraped_at=None):
    db = SessionLocal()
    inserted = 0
    reached_old = False
    try:
        for job_post in jobs:
            job_post_obj = create_job_post(job_post)

            if last_scraped_at and job_post_obj.published_date and job_post_obj.published_date <= last_scraped_at.replace(tzinfo=None):
                db.commit()
                reached_old = True
                return inserted, reached_old

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
    return inserted, reached_old

def create_job_post(jobs_raw):
    return JobPost(
        id=jobs_raw['id'],
        source=jobs_raw.get('source', 'gupy'),
        company_id=jobs_raw.get('companyId') or jobs_raw.get('company_id'),
        name=jobs_raw['name'],
        description=jobs_raw.get('description'),
        career_page_id=jobs_raw.get('careerPageId') or jobs_raw.get('career_page_id'),
        career_page_name=jobs_raw.get('careerPageName') or jobs_raw.get('career_page_name'),
        career_page_logo=jobs_raw.get('careerPageLogo') or jobs_raw.get('career_page_logo'),
        career_page_url=jobs_raw.get('careerPageUrl') or jobs_raw.get('career_page_url'),
        job_type=jobs_raw.get('type') or jobs_raw.get('job_type'),
        published_date=parse_datetime(jobs_raw.get("publishedDate") or jobs_raw.get("published_date")),
        application_deadline=parse_date(jobs_raw.get("applicationDeadline") or jobs_raw.get("application_deadline")),
        is_remote_work=jobs_raw.get('isRemoteWork') if 'isRemoteWork' in jobs_raw else jobs_raw.get('is_remote_work'),
        city=jobs_raw.get('city'),
        state=jobs_raw.get('state'),
        country=jobs_raw.get('country'),
        job_url=jobs_raw.get('jobUrl') or jobs_raw.get('job_url'),
        workplace_type=jobs_raw.get('workplaceType') or jobs_raw.get('workplace_type'),
        disabilities=jobs_raw.get('disabilities'),
        skills=json.dumps(jobs_raw.get("skills"), ensure_ascii=False) if isinstance(jobs_raw.get("skills"), (list, dict)) else jobs_raw.get("skills"),
        badges=json.dumps(jobs_raw.get("badges"), ensure_ascii=False) if isinstance(jobs_raw.get("badges"), (list, dict)) else jobs_raw.get("badges"),
        region=jobs_raw.get('region', 'Latin America'),
        country_code=jobs_raw.get('country_code', 'BR'),
        currency=jobs_raw.get('currency', 'BRL'),
        fingerprint=jobs_raw.get('fingerprint'),
    )

def _build_pagination(total_items: int, page: int, page_size: int) -> dict:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    return {
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def get_jobs_posts(
    *,
    search: str | None = None,
    source: str | None = None,
    region: str | None = None,
    country_code: str | None = None,
    workplace_type: str | None = None,
    sort: str = "published_date",
    order: str = "desc",
    page: int | None = None,
    page_size: int | None = None,
    paginated: bool = False,
):
    db = SessionLocal()
    try:
        query = Select(JobPost)

        if search:
            search_value = f"%{search.strip()}%"
            query = query.where(
                or_(
                    JobPost.name.ilike(search_value),
                    JobPost.career_page_name.ilike(search_value),
                    JobPost.city.ilike(search_value),
                    JobPost.state.ilike(search_value),
                    JobPost.country.ilike(search_value),
                )
            )

        if source:
            query = query.where(JobPost.source.ilike(source.strip()))

        if region:
            query = query.where(JobPost.region.ilike(region.strip()))

        if country_code:
            query = query.where(JobPost.country_code.ilike(country_code.strip()))

        if workplace_type:
            query = query.where(JobPost.workplace_type.ilike(workplace_type.strip()))

        sort_map = {
            "id": JobPost.id,
            "name": JobPost.name,
            "company": JobPost.career_page_name,
            "published_date": JobPost.published_date,
            "workplace_type": JobPost.workplace_type,
            "source": JobPost.source,
        }
        sort_column = sort_map.get(sort, JobPost.published_date)
        if order.lower() == "asc":
            query = query.order_by(sort_column.asc().nullslast(), JobPost.id.asc())
        else:
            query = query.order_by(sort_column.desc().nullslast(), JobPost.id.desc())

        if not paginated:
            return db.scalars(query).all()

        safe_page = max(1, page or 1)
        safe_page_size = max(1, min(page_size or 20, 100))
        total_items = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = db.scalars(
            query.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
        ).all()
        return {
            "items": [job_post.to_dict() for job_post in items],
            "pagination": _build_pagination(total_items, safe_page, safe_page_size),
        }
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
