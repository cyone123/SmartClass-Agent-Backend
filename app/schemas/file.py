from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.response import BaseResponse

KnowledgeFileStatus = Literal["uploaded", "indexing", "ready", "failed", "deleted"]


class KnowledgeFile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    original_name: str
    stored_name: str
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str
    storage_path: str
    status: KnowledgeFileStatus
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None


class KnowledgeFileResponse(BaseResponse[KnowledgeFile]):
    pass


class KnowledgeFileListResponse(BaseResponse[list[KnowledgeFile]]):
    pass


class AttachmentFile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    thread_id: str
    original_name: str
    stored_name: str
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str
    storage_path: str
    created_at: datetime
    updated_at: datetime


class AttachmentFileResponse(BaseResponse[AttachmentFile]):
    pass
