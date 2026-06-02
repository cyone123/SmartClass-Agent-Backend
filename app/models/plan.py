from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.file import AttachmentFile
    from app.models.file import ArtifactFile
    from app.models.file import KnowledgeFile
    from app.models.session import Session
    from app.models.user import User

class Plan(Base):
    __tablename__ = "teaching_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user: Mapped[User] = relationship("User", back_populates="plans")
    sessions: Mapped[list[Session]] = relationship(
        "Session",
        back_populates="plan",
        order_by="Session.id",
    )
    files: Mapped[list[KnowledgeFile]] = relationship(
        "KnowledgeFile",
        back_populates="plan",
        order_by="KnowledgeFile.id",
    )
    attachments: Mapped[list[AttachmentFile]] = relationship(
        "AttachmentFile",
        back_populates="plan",
        order_by="AttachmentFile.id",
    )
    artifacts: Mapped[list[ArtifactFile]] = relationship(
        "ArtifactFile",
        back_populates="plan",
        order_by="ArtifactFile.id",
    )
