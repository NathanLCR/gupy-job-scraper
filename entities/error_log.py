from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="scraper")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
