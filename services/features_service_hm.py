from collections import defaultdict
from datetime import datetime, timedelta, UTC

from sqlalchemy import select, func, Date
from database import SessionLocal
from entities.associations import job_hard_skills
from entities import JobPost, Job, City, HardSkill, ContractType

def get_average_job_post_daily():
    db = SessionLocal()
    subquery = (
        select(func.count(JobPost.id).label("daily_count"))
        .group_by(func.cast(JobPost.published_date, Date))
        .subquery()
    )
    query = select(func.avg(subquery.c.daily_count))
    result = db.execute(query).scalar()
    db.close()
    return result

def get_average_salary():
    db = SessionLocal()
    query = select(func.avg(Job.salary))
    result = db.execute(query).scalar()
    db.close()
    return result

def get_top_technologies(n = 10):
    db = SessionLocal()
    query = (
        select(HardSkill.name, func.count(job_hard_skills.c.job_id).label("count"))
        .join(job_hard_skills, HardSkill.id == job_hard_skills.c.hard_skill_id)
        .group_by(HardSkill.name)
        .order_by(func.count(job_hard_skills.c.job_id).desc())
        .limit(n)
    )
    result = db.execute(query).all()
    db.close()
    return [{"name": row[0], "count": row[1]} for row in result]

def get_top_locations(n = 10):
    db = SessionLocal()
    query = (
        select(City.name, func.count(Job.id).label("count"))
        .join(Job, City.id == Job.city_id)
        .group_by(City.name)
        .order_by(func.count(Job.id).desc())
        .limit(n)
    )
    result = db.execute(query).all()
    db.close()
    return [{"name": row[0], "count": row[1]} for row in result]

def get_jobs_by_contract_type():
    db = SessionLocal()
    query = (
        select(ContractType.name, func.count(Job.id).label("count"))
        .join(Job, ContractType.id == Job.contract_type_id)
        .group_by(ContractType.name)
        .order_by(func.count(Job.id).desc())
    )
    result = db.execute(query).all()
    db.close()
    return [{"name": row[0], "count": row[1]} for row in result]

def get_jobs_by_seniority():
    db = SessionLocal()
    query = (
        select(Job.seniority, func.count(Job.id).label("count"))
        .filter(Job.seniority != None)
        .group_by(Job.seniority)
        .order_by(func.count(Job.id).desc())
    )
    result = db.execute(query).all()
    db.close()
    return [{"name": row[0], "count": row[1]} for row in result]


def get_technology_trends(days=30, limit=5, skill=None):
    db = SessionLocal()
    days = max(7, min(int(days), 90))
    limit = max(1, min(int(limit), 10))
    requested_skill = (skill or "").strip()

    today = datetime.now(UTC).date()
    since_date = today - timedelta(days=days - 1)
    since_dt = datetime.combine(since_date, datetime.min.time())
    period_expr = func.date(JobPost.published_date)

    query = (
        select(
            period_expr.label("period"),
            HardSkill.name.label("technology"),
            func.count(Job.id).label("count"),
        )
        .select_from(Job)
        .join(JobPost, JobPost.id == Job.id)
        .join(job_hard_skills, job_hard_skills.c.job_id == Job.id)
        .join(HardSkill, HardSkill.id == job_hard_skills.c.hard_skill_id)
        .where(JobPost.published_date.is_not(None))
        .where(JobPost.published_date >= since_dt)
    )

    if requested_skill:
        query = query.where(func.lower(HardSkill.name) == requested_skill.lower())

    query = query.group_by(period_expr, HardSkill.name).order_by(period_expr.asc(), HardSkill.name.asc())

    rows = db.execute(query).all()
    db.close()

    periods = [(since_date + timedelta(days=offset)).isoformat() for offset in range(days)]
    if not rows:
        return {
            "days": days,
            "periods": periods,
            "series": [],
            "selected_skill": requested_skill or None,
        }

    totals = defaultdict(int)
    counts_by_skill = defaultdict(dict)

    for period, technology, count in rows:
        period_key = period.isoformat() if hasattr(period, "isoformat") else str(period)
        totals[technology] += count
        counts_by_skill[technology][period_key] = count

    if requested_skill:
        top_technologies = sorted(totals.keys())
    else:
        top_technologies = [
            name
            for name, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    series = [
        {
            "name": technology,
            "counts": [counts_by_skill[technology].get(period, 0) for period in periods],
            "total": totals[technology],
        }
        for technology in top_technologies
    ]

    return {
        "days": days,
        "periods": periods,
        "series": series,
        "selected_skill": requested_skill or None,
    }
