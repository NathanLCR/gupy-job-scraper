from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import JSON, Integer, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base
from entities.types import Vector


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_skills: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    seniority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_region: Mapped[str | None] = mapped_column(String(50), nullable=True, default="Global")
    target_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Dense Vector Embedding for candidate representation (384-dimensional)
    embedding = mapped_column(Vector(384), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "raw_resume_text": self.raw_resume_text,
            "parsed_skills": self.parsed_skills or {},
            "seniority": self.seniority,
            "target_region": self.target_region,
            "target_role": self.target_role,
            "years_experience": self.years_experience,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
