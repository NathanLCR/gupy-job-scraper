from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.associations import job_hard_skills
from entities.base import Base


class HardSkill(Base):
    __tablename__ = "hard_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    jobs = relationship("Job", secondary=job_hard_skills, back_populates="hard_skills")