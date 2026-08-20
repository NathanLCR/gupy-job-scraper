from datetime import date, datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class JobPost(Base):
    __tablename__ = "jobs_posts"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_page_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    career_page_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    career_page_logo: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    application_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_remote_work: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    workplace_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    disabilities: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    badges: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Multi-Region & Ingestion Fields
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="gupy", index=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False, default="Latin America")
    country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="BR")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="BRL")
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "company_id": self.company_id,
            "name": self.name,
            "description": self.description,
            "career_page_id": self.career_page_id,
            "career_page_name": self.career_page_name,
            "career_page_logo": self.career_page_logo,
            "career_page_url": self.career_page_url,
            "job_type": self.job_type,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "application_deadline": self.application_deadline.isoformat() if self.application_deadline else None,
            "is_remote_work": self.is_remote_work,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "job_url": self.job_url,
            "workplace_type": self.workplace_type,
            "disabilities": self.disabilities,
            "skills": self.skills,
            "badges": self.badges,
            "region": self.region,
            "country_code": self.country_code,
            "currency": self.currency,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }