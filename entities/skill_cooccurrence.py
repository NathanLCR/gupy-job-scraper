from datetime import datetime
from sqlalchemy import Integer, String, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class SkillCooccurrence(Base):
    __tablename__ = "skill_cooccurrences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_a: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    skill_b: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    pair_key: Mapped[str] = mapped_column(String(300), unique=True, index=True, nullable=False)
    cooccurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    region: Mapped[str] = mapped_column(String(50), nullable=False, default="Global")

    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("pair_key", name="uq_skill_cooccurrences_pair_key"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "skill_a": self.skill_a,
            "skill_b": self.skill_b,
            "pair_key": self.pair_key,
            "cooccurrence_count": self.cooccurrence_count,
            "region": self.region,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }
