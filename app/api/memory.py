from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.agent import AgentRuntime, get_agent_runtime
from app.core.auth import get_current_user
from app.core.memory import (
    delete_memory_item,
    experience_namespace,
    normalize_user_id,
    profile_namespace,
    put_memory_item,
    search_memory_items,
)
from app.models.user import User
from app.schemas.memory import (
    MemoryItem,
    MemoryItemResponse,
    MemoryKind,
    MemoryList,
    MemoryListResponse,
    MemoryUpdateRequest,
    MemoryWriteRequest,
)
from app.schemas.response import success_response

router = APIRouter()


def _namespace_for_kind(user_id: str | None, kind: MemoryKind) -> tuple[str, ...]:
    if kind == "profile":
        return profile_namespace(user_id)
    return experience_namespace(user_id)


def _serialize_memory(raw: dict, *, kind: MemoryKind) -> MemoryItem:
    content = str(raw.get("content") or raw.get("summary") or "")
    summary = str(raw.get("summary") or content[:240])
    return MemoryItem(
        id=str(raw.get("id") or ""),
        kind=kind,
        title=str(raw.get("title") or "Memory"),
        summary=summary,
        content=content,
        tags=[str(tag) for tag in raw.get("tags") or []],
        source_thread_id=raw.get("source_thread_id"),
        source_plan_id=raw.get("source_plan_id"),
        created_at=str(raw.get("created_at") or "") or None,
        updated_at=str(raw.get("updated_at") or "") or None,
    )


@router.get("/memory", response_model=MemoryListResponse)
async def list_memories(
    kind: MemoryKind | None = Query(default=None),
    query: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
) -> MemoryListResponse:
    normalized_user_id = normalize_user_id(str(current_user.id))
    kinds: list[MemoryKind] = [kind] if kind is not None else ["profile", "experience"]
    items: list[MemoryItem] = []
    for memory_kind in kinds:
        raw_items = await search_memory_items(
            agent_runtime.memory_store,
            _namespace_for_kind(normalized_user_id, memory_kind),
            limit=100,
        )
        if query:
            keyword = query.casefold()
            raw_items = [
                item
                for item in raw_items
                if keyword in str(item.get("title") or "").casefold()
                or keyword in str(item.get("summary") or "").casefold()
                or keyword in str(item.get("content") or "").casefold()
            ]
        items.extend(_serialize_memory(raw, kind=memory_kind) for raw in raw_items)
    items.sort(key=lambda item: item.updated_at or "", reverse=True)
    return success_response(
        data=MemoryList(items=items),
        response_model=MemoryListResponse,
    )


@router.post("/memory", response_model=MemoryItemResponse)
async def create_memory(
    payload: MemoryWriteRequest,
    current_user: User = Depends(get_current_user),
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
) -> MemoryItemResponse:
    user_id = normalize_user_id(str(current_user.id))
    value = {
        "kind": payload.kind,
        "title": payload.title.strip(),
        "summary": (payload.summary or payload.content[:240]).strip(),
        "content": payload.content.strip(),
        "tags": [tag.strip() for tag in payload.tags if tag.strip()],
    }
    if not value["title"] or not value["content"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="title and content are required.",
        )
    raw = await put_memory_item(
        agent_runtime.memory_store,
        _namespace_for_kind(user_id, payload.kind),
        value=value,
    )
    return success_response(
        data=_serialize_memory(raw, kind=payload.kind),
        response_model=MemoryItemResponse,
    )


@router.put("/memory/{kind}/{memory_id}", response_model=MemoryItemResponse)
async def update_memory(
    kind: MemoryKind,
    memory_id: str,
    payload: MemoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
) -> MemoryItemResponse:
    user_id = normalize_user_id(str(current_user.id))
    update: dict = {"kind": kind}
    if payload.title is not None:
        update["title"] = payload.title.strip()
    if payload.content is not None:
        update["content"] = payload.content.strip()
    if payload.summary is not None:
        update["summary"] = payload.summary.strip()
    elif payload.content is not None:
        update["summary"] = payload.content.strip()[:240]
    if payload.tags is not None:
        update["tags"] = [tag.strip() for tag in payload.tags if tag.strip()]

    raw = await put_memory_item(
        agent_runtime.memory_store,
        _namespace_for_kind(user_id, kind),
        value=update,
        key=memory_id,
    )
    return success_response(
        data=_serialize_memory(raw, kind=kind),
        response_model=MemoryItemResponse,
    )


@router.delete("/memory/{kind}/{memory_id}")
async def delete_memory(
    kind: MemoryKind,
    memory_id: str,
    current_user: User = Depends(get_current_user),
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
):
    await delete_memory_item(
        agent_runtime.memory_store,
        _namespace_for_kind(normalize_user_id(str(current_user.id)), kind),
        memory_id,
    )
    return success_response(data={"deleted": True})
