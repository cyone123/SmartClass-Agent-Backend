import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent import AgentRuntime, get_agent_runtime
from app.dependencies.db import get_db
from app.schemas.chat import ChatRequest
from app.services import file_service, session_service

router = APIRouter()


def format_sse_event(data: str, *, event: str | None = None) -> str:
    payload = ""
    if event:
        payload += f"event: {event}\n"
    normalized_data = data.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalized_data.split("\n") or [normalized_data]:
        payload += f"data: {line}\n"
    return payload + "\n"


@router.post("/chat/stream")
async def chat(
    message: ChatRequest,
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
    db: AsyncSession = Depends(get_db),
):
    thread_id = message.thread_id
    attachment_ids = message.attachment_ids or []
    if attachment_ids and not thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_id is required when attachment_ids are provided.",
        )

    plan_id = None
    if thread_id:
        session = await session_service.get_session_by_thread_id(db, thread_id)
        if session is not None:
            plan_id = session.plan_id

    attachment_text = ""
    if attachment_ids:
        if plan_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Thread {thread_id} not found.",
            )
        attachment_paths = await file_service.get_attachment_storage_paths_by_ids(
            db,
            plan_id=plan_id,
            thread_id=thread_id,
            attachment_ids=attachment_ids,
        )
        attachment_text = await file_service.parse_attachment_files(message.message, attachment_paths, agent_runtime)

    async def event_stream():
        metadata = json.dumps({"thread_id": thread_id}, ensure_ascii=False)
        yield format_sse_event(metadata, event="metadata")

        async for data in agent_runtime.stream_agent_response(
            message.message,
            thread_id,
            plan_id=plan_id,
            attachment_text=attachment_text or None,
        ):
            yield format_sse_event(data, event="message")

        yield format_sse_event("[DONE]", event="done")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-ID": thread_id or "",
        },
    )
