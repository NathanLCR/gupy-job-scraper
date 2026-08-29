from datetime import datetime
from typing import Optional, List
from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.associations import (
    job_hard_skills,
    job_nice_to_have_skills,
    job_soft_skills,
)
from entities.base import Base
from entities.types import Vector


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    extractor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="regex")
    salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tech_stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Multi-Region & Ingestion Fields
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="gupy", index=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False, default="Latin America")
    country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="BR")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="BRL")
    workplace_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Dense Vector Embedding (384-dimensional for sentence-transformers / HNSW)
    embedding = mapped_column(Vector(384), nullable=True)
    search_document = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relational Foreign Keys
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    contract_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_types.id"),
        nullable=True,
    )
    state_id: Mapped[int | None] = mapped_column(ForeignKey("states.id"), nullable=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
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
            "source": self.source,
            "job_title": self.job_title,
            "extractor_type": self.extractor_type,
            "salary": self.salary,
            "seniority": self.seniority,
            "years_experience": self.years_experience,
            "tech_stack": self.tech_stack or [],
            "description": self.description,
            "region": self.region,
            "country_code": self.country_code,
            "currency": self.currency,
            "workplace_type": self.workplace_type,
            "fingerprint": self.fingerprint,
            "company_id": self.company_id,
            "contract_type_id": self.contract_type_id,
            "state_id": self.state_id,
            "city_id": self.city_id,
            "company": self.company.name if self.company else None,
            "contract_type": self.contract_type.name if self.contract_type else None,
            "state": self.state.name if self.state else None,
            "city": self.city.name if self.city else None,
            "hard_skills": [skill.name for skill in (self.hard_skills or [])],
            "soft_skills": [skill.name for skill in (self.soft_skills or [])],
            "nice_to_have_skills": [skill.name for skill in (self.nice_to_have_skills or [])],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
