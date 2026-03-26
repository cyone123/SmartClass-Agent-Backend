from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.session import Session

class Plan(Base):
    __tablename__ = "teaching_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sessions: Mapped[list[Session]] = relationship(
        "Session",
        back_populates="plan",
        order_by="Session.id",
    )
