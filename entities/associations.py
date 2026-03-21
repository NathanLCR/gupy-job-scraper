from sqlalchemy import Column, ForeignKey, Table

from entities.base import Base


job_hard_skills = Table(
    "job_hard_skills",
    Base.metadata,
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
    Column("hard_skill_id", ForeignKey("hard_skills.id"), primary_key=True),
)

job_soft_skills = Table(
    "job_soft_skills",
    Base.metadata,
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
    Column("soft_skill_id", ForeignKey("soft_skills.id"), primary_key=True),
)

job_nice_to_have_skills = Table(
    "job_nice_to_have_skills",
    Base.metadata,
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
    Column("nice_to_have_skill_id", ForeignKey("nice_to_have_skills.id"), primary_key=True),
)
