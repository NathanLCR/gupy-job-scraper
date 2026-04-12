from services.error_service import log_error
from entities.job import Job
from entities.city import City
from entities.company import Company
from entities.state import State
from sqlalchemy import Select, func, or_, select
from database import SessionLocal

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


def get_jobs(
    *,
    search: str | None = None,
    location: str | None = None,
    sort: str = "id",
    order: str = "desc",
    page: int | None = None,
    page_size: int | None = None,
    paginated: bool = False,
):
    db = SessionLocal()
    try:
        query = (
            Select(Job)
            .outerjoin(Company, Job.company_id == Company.id)
            .outerjoin(City, Job.city_id == City.id)
            .outerjoin(State, Job.state_id == State.id)
        )

        if search:
            search_value = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Job.job_title.ilike(search_value),
                    Company.name.ilike(search_value),
                    City.name.ilike(search_value),
                    State.name.ilike(search_value),
                )
            )

        if location:
            location_value = f"%{location.strip()}%"
            query = query.where(
                or_(
                    City.name.ilike(location_value),
                    State.name.ilike(location_value),
                )
            )

        sort_map = {
            "id": Job.id,
            "title": Job.job_title,
            "company": Company.name,
            "salary": Job.salary,
            "location": City.name,
        }
        sort_column = sort_map.get(sort, Job.id)
        if order.lower() == "asc":
            query = query.order_by(sort_column.asc().nullslast(), Job.id.asc())
        else:
            query = query.order_by(sort_column.desc().nullslast(), Job.id.desc())

        if not paginated:
            return db.scalars(query).all()

        safe_page = max(1, page or 1)
        safe_page_size = max(1, min(page_size or 20, 100))
        total_items = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = db.scalars(
            query.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
        ).all()
        return {
            "items": [job.to_dict() for job in items],
            "pagination": _build_pagination(total_items, safe_page, safe_page_size),
        }
    finally:
        db.close()

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
