from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.associations import (
    job_hard_skills,
    job_nice_to_have_skills,
    job_soft_skills,
)
from entities.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tech_stack: Mapped[list[str]] = mapped_column(JSON, default=list)

    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    contract_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_types.id"),
        nullable=True,
    )
    state_id: Mapped[int | None] = mapped_column(ForeignKey("states.id"), nullable=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), nullable=True)

    company = relationship("Company", back_populates="jobs")
    contract_type = relationship("ContractType", back_populates="jobs")
    state = relationship("State", back_populates="jobs")
    city = relationship("City", back_populates="jobs")

    hard_skills = relationship(
        "HardSkill",
        secondary=job_hard_skills,
        back_populates="jobs",
    )
    soft_skills = relationship(
        "SoftSkill",
        secondary=job_soft_skills,
        back_populates="jobs",
    )
    nice_to_have_skills = relationship(
        "NiceToHaveSkill",
        secondary=job_nice_to_have_skills,
        back_populates="jobs",
    )
        