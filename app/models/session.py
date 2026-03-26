from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.plan import Plan

class Session(Base):
    __tablename__ = "teaching_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teaching_plans.id"),
        nullable=False,
    )
    plan: Mapped[Plan] = relationship("Plan", back_populates="sessions")
