from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from entities.base import Base


class SearchTerm(Base):
    __tablename__ = "search_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "term": self.term,
            "is_active": self.is_active,
        }