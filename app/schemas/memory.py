from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.response import BaseResponse


MemoryKind = Literal["profile", "experience"]


class MemoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: MemoryKind
    title: str
    summary: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source_thread_id: str | None = None
    source_plan_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemoryList(BaseModel):
    items: list[MemoryItem]


class MemoryListResponse(BaseResponse[MemoryList]):
    pass


class MemoryItemResponse(BaseResponse[MemoryItem]):
    pass


class MemoryWriteRequest(BaseModel):
    user_id: str | None = None
    kind: MemoryKind
    title: str
    summary: str | None = None
    content: str
    tags: list[str] = Field(default_factory=list)


class MemoryUpdateRequest(BaseModel):
    user_id: str | None = None
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    tags: list[str] | None = None

