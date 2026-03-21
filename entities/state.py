from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.base import Base


class State(Base):
    __tablename__ = "states"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    cities = relationship("City", back_populates="state")
    jobs = relationship("Job", back_populates="state")
