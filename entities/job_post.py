from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class JobPost(Base):
    __tablename__ = "jobs_posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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

    def to_dict(self):
        return {
            "id": self.id,
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
        }