import json
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.agent import stream_agent_response
from app.schemas.chat import ChatRequest

router = APIRouter()


def format_sse_event(data: str, *, event: str | None = None) -> str:
    payload = ""
    if event:
        payload += f"event: {event}\n"
    for line in data.splitlines() or [data]:
        payload += f"data: {line}\n"
    return payload + "\n"


@router.post("/chat/stream")
async def chat(message: ChatRequest):
    thread_id = message.thread_id or uuid4().hex

    def event_stream():
        metadata = json.dumps({"thread_id": thread_id}, ensure_ascii=False)
        yield format_sse_event(metadata, event="metadata")

        for data in stream_agent_response(message.message, thread_id):
            yield format_sse_event(data, event="message")

        yield format_sse_event("[DONE]", event="done")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-ID": thread_id,
        },
    )
