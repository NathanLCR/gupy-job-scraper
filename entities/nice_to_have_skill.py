from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.associations import job_nice_to_have_skills
from entities.base import Base


class NiceToHaveSkill(Base):
    __tablename__ = "nice_to_have_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    jobs = relationship(
        "Job",
        secondary=job_nice_to_have_skills,
        back_populates="nice_to_have_skills",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
        }