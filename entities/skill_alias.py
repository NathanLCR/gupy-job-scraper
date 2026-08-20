from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="technical")
    esco_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onet_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "alias": self.alias,
            "canonical_name": self.canonical_name,
            "category": self.category,
            "esco_uri": self.esco_uri,
            "onet_code": self.onet_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
