from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class JobsPost(Base):
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