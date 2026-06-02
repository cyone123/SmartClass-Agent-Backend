from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.file import ArtifactFile, AttachmentFile, KnowledgeFile
    from app.models.plan import Plan
    from app.models.session import Session


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="teacher", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    plans: Mapped[list[Plan]] = relationship("Plan", back_populates="user")
    sessions: Mapped[list[Session]] = relationship("Session", back_populates="user")
    knowledge_files: Mapped[list[KnowledgeFile]] = relationship("KnowledgeFile", back_populates="user")
    attachment_files: Mapped[list[AttachmentFile]] = relationship("AttachmentFile", back_populates="user")
    artifact_files: Mapped[list[ArtifactFile]] = relationship("ArtifactFile", back_populates="user")
