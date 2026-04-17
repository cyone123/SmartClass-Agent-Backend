import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent import AgentRuntime, get_agent_runtime
from app.models.file import AttachmentFile
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


def format_sse_json_event(payload: object, *, event: str) -> str:
    return format_sse_event(
        json.dumps(jsonable_encoder(payload), ensure_ascii=False),
        event=event,
    )


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
    attachments: list[AttachmentFile] | None = None
    if thread_id:
        session = await session_service.get_session_by_thread_id(db, thread_id)
        if session is not None:
            plan_id = session.plan_id

    if attachment_ids:
        if plan_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Thread {thread_id} not found.",
            )
        attachments = await file_service.get_chat_attachments_by_ids(
            db,
            plan_id=plan_id,
            thread_id=thread_id,
            attachment_ids=attachment_ids,
        )

    async def event_stream():
        run_id = uuid4().hex
        yield format_sse_json_event(
            {"thread_id": thread_id, "run_id": run_id},
            event="metadata",
        )

        async for event in agent_runtime.stream_agent_events(
            message.message,
            thread_id,
            run_id=run_id,
            plan_id=plan_id,
            attachments=attachments,
        ):
            event_name = event.get("event")
            payload = event.get("data")

            if event_name in {"progress", "token", "error", "suggestions", "artifact"}:
                yield format_sse_json_event(payload, event=event_name)

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
