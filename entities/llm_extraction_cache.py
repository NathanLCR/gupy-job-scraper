from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class LLMExtractionCache(Base):
    """
    Persistent SHA-256 extraction cache table.
    Ensures that identical job postings and candidate profiles are never
    sent to cloud LLMs (Groq / OpenRouter) more than once, saving quota and latency.
    """
    __tablename__ = "llm_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="groq")
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="llama-3.3-70b-versatile")
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1.0")
    response_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "response_json": self.response_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
