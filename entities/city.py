from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.base import Base


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), nullable=False)

    state = relationship("State", back_populates="cities")
    jobs = relationship("Job", back_populates="city")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "state_id": self.state_id,
        }