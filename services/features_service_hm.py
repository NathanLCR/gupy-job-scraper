from sqlalchemy import select, func, Date
from database import SessionLocal
from entities.associations import job_hard_skills
from entities import JobPost, Job, City, HardSkill

def get_average_job_post_daily():
    db = SessionLocal()
    subquery = (
        select(func.count(JobPost.id).label("daily_count"))
        .group_by(func.cast(JobPost.published_date, Date))
        .subquery()
    )
    query = select(func.avg(subquery.c.daily_count))
    result = db.execute(query).scalar()
    return result

def get_average_salary():
    db = SessionLocal()
    query = select(func.avg(Job.salary))
    result = db.execute(query).scalar()
    return result

def get_top_5_technologies():
    db = SessionLocal()
    query = (
        select(HardSkill.name, func.count(job_hard_skills.c.job_id).label("count"))
        .join(job_hard_skills, HardSkill.id == job_hard_skills.c.hard_skill_id)
        .group_by(HardSkill.name)
        .order_by(func.count(job_hard_skills.c.job_id).desc())
        .limit(5)
    )
    result = db.execute(query).all()
    return [{"name": row[0], "count": row[1]} for row in result]

def get_top_5_locations():
    db = SessionLocal()
    query = (
        select(City.name, func.count(Job.id).label("count"))
        .join(Job, City.id == Job.city_id)
        .group_by(City.name)
        .order_by(func.count(Job.id).desc())
        .limit(5)
    )
    result = db.execute(query).all()
    return [{"name": row[0], "count": row[1]} for row in result]