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
    extractor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tech_stack: Mapped[list[str]] = mapped_column(JSON, default=list)

    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    contract_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_types.id"),
        nullable=True,
    )
    state_id: Mapped[int | None] = mapped_column(ForeignKey("states.id"), nullable=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), nullable=True)

    company = relationship("Company", back_populates="jobs", lazy="joined")
    contract_type = relationship("ContractType", back_populates="jobs", lazy="joined")
    state = relationship("State", back_populates="jobs", lazy="joined")
    city = relationship("City", back_populates="jobs", lazy="joined")

    hard_skills = relationship(
        "HardSkill",
        secondary=job_hard_skills,
        back_populates="jobs",
        lazy="subquery",
    )
    soft_skills = relationship(
        "SoftSkill",
        secondary=job_soft_skills,
        back_populates="jobs",
        lazy="subquery",
    )
    nice_to_have_skills = relationship(
        "NiceToHaveSkill",
        secondary=job_nice_to_have_skills,
        back_populates="jobs",
        lazy="subquery",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "job_title": self.job_title,
            "extractor_type": self.extractor_type,
            "salary": self.salary,
            "seniority": self.seniority,
            "years_experience": self.years_experience,
            "tech_stack": self.tech_stack,
            "company_id": self.company_id,
            "contract_type_id": self.contract_type_id,
            "state_id": self.state_id,
            "city_id": self.city_id,
            "company": self.company.name if self.company else None,
            "contract_type": self.contract_type.name if self.contract_type else None,
            "state": self.state.name if self.state else None,
            "city": self.city.name if self.city else None,
            "hard_skills": [skill.name for skill in self.hard_skills],
            "soft_skills": [skill.name for skill in self.soft_skills],
            "nice_to_have_skills": [skill.name for skill in self.nice_to_have_skills],
        }
        