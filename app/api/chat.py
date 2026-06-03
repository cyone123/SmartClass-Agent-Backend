import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.agent import AgentRuntime, get_agent_runtime
from app.core.observability import (
    RunContext,
    get_observation_sink,
    log_observation,
)
from app.models.file import AttachmentFile
from app.models.user import User
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
    current_user: User = Depends(get_current_user),
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
    db: AsyncSession = Depends(get_db),
):
    thread_id = message.thread_id
    attachment_ids = message.attachment_ids or []
    approval = message.approval.model_dump() if message.approval is not None else None
    if attachment_ids and not thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_id is required when attachment_ids are provided.",
        )
    if approval and not thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_id is required when approval is provided.",
        )

    plan_id = None
    attachments: list[AttachmentFile] | None = None
    if thread_id:
        session = await session_service.get_session_by_thread_id(db, thread_id, user_id=current_user.id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Thread {thread_id} not found.",
            )
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
            user_id=current_user.id,
        )

    if approval:
        try:
            await agent_runtime.validate_approval_request(thread_id, approval["interrupt_id"])
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    async def event_stream():
        run_id = uuid4().hex
        run_context = RunContext(
            run_id=run_id,
            thread_id=thread_id,
            plan_id=plan_id,
            user_id=str(current_user.id),
            agent_name="chat_stream",
        )
        observation_sink = get_observation_sink()
        yield format_sse_json_event(
            {"thread_id": thread_id, "run_id": run_id},
            event="metadata",
        )

        log_observation(
            "chat.stream.request",
            context=run_context,
            sink=observation_sink,
            status="running",
            fields={
                "message_size": len(message.message or ""),
                "attachment_count": len(attachment_ids),
                "has_approval": bool(approval),
            },
        )
        try:
            async for event in agent_runtime.stream_agent_events(
                message.message or "",
                thread_id,
                run_id=run_id,
                user_id=str(current_user.id),
                plan_id=plan_id,
                attachments=attachments,
                approval=approval,
                run_context=run_context,
                observation_sink=observation_sink,
            ):
                event_name = event.get("event")
                payload = event.get("data")

                if event_name in {
                    "progress",
                    "token",
                    "error",
                    "suggestions",
                    "artifact",
                    "artifact_trace",
                    "approval",
                }:
                    yield format_sse_json_event(payload, event=event_name)
            log_observation(
                "chat.stream.completed",
                context=run_context,
                sink=observation_sink,
                status="success",
            )
        except Exception as exc:
            log_observation(
                "chat.stream.failed",
                context=run_context,
                sink=observation_sink,
                status="failed",
                fields={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            yield format_sse_json_event(
                {"run_id": run_id, "message": "对话处理失败，请稍后重试。"},
                event="error",
            )

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
