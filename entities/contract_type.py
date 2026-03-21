from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from entities.base import Base


class ContractType(Base):
    __tablename__ = "contract_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    jobs = relationship("Job", back_populates="contract_type")
