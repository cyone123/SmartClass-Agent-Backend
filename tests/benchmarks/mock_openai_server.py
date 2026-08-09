"""Small OpenAI-compatible mock server for separating service overhead from LLM latency."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="SmartClass benchmark Mock LLM")
CALL_COUNTS: Counter[str] = Counter()
LAST_REQUEST: dict[str, Any] = {}


def _delay_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("MOCK_LLM_DELAY_MS", "20")) / 1000)
    except ValueError:
        return 0.02


def _schema_value(schema: Mapping[str, Any] | None) -> Any:
    if not isinstance(schema, Mapping):
        return None
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    for key in ("anyOf", "oneOf"):
        variants = schema.get(key)
        if isinstance(variants, list):
            for variant in variants:
                if isinstance(variant, Mapping) and variant.get("type") != "null":
                    return _schema_value(variant)
    schema_type = schema.get("type")
    if schema_type == "object" or isinstance(schema.get("properties"), Mapping):
        properties = schema.get("properties") or {}
        if not isinstance(properties, Mapping):
            return {}
        return {str(name): _schema_value(value) for name, value in properties.items()}
    if schema_type == "array":
        return []
    if schema_type == "boolean":
        return False
    if schema_type in {"integer", "number"}:
        return 0
    if schema_type == "string":
        return "mock"
    return None


def _structured_arguments(body: Mapping[str, Any]) -> tuple[str, str, str]:
    # LangChain/OpenAI clients can include a tools declaration alongside a
    # JSON-schema response format.  The response contract is determined by
    # response_format in that case; returning a tool call would make the
    # json_schema parser report ``parsed=None`` even though the payload is
    # otherwise valid.
    response_format = body.get("response_format")
    if isinstance(response_format, Mapping):
        json_schema = response_format.get("json_schema")
        schema = json_schema.get("schema") if isinstance(json_schema, Mapping) else None
        name = str(json_schema.get("name") if isinstance(json_schema, Mapping) else "structured_response")
        return name, json.dumps(_schema_value(schema), ensure_ascii=False, separators=(",", ":")), "json_schema"

    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        tool = tools[0] if isinstance(tools[0], Mapping) else {}
        function = tool.get("function") if isinstance(tool, Mapping) else {}
        function = function if isinstance(function, Mapping) else {}
        name = str(function.get("name") or "structured_response")
        parameters = function.get("parameters")
        return name, json.dumps(_schema_value(parameters), ensure_ascii=False, separators=(",", ":")), "tool_call"

    return "", "", ""


def _usage(body: Mapping[str, Any], completion_chars: int) -> dict[str, int]:
    prompt_tokens = max(1, len(json.dumps(body, ensure_ascii=False, default=str)) // 4)
    completion_tokens = max(1, completion_chars // 4)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _completion_response(body: Mapping[str, Any]) -> dict[str, Any]:
    completion_id = f"mock-{uuid.uuid4().hex}"
    tool_name, arguments, response_kind = _structured_arguments(body)
    if response_kind == "tool_call":
        message: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": arguments},
                }
            ],
        }
        finish_reason = "tool_calls"
        completion_size = len(arguments)
    elif response_kind == "json_schema":
        message = {"role": "assistant", "content": arguments}
        finish_reason = "stop"
        completion_size = len(arguments)
    else:
        content = os.getenv("MOCK_LLM_RESPONSE", "Mock LLM response.")
        message = {"role": "assistant", "content": content}
        finish_reason = "stop"
        completion_size = len(content)

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(body.get("model") or "mock-model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": _usage(body, completion_size),
    }


async def _stream_response(body: Mapping[str, Any]) -> AsyncIterator[str]:
    completion_id = f"mock-{uuid.uuid4().hex}"
    content = os.getenv("MOCK_LLM_RESPONSE", "Mock LLM response.")
    parts = [content] if len(content) <= 8 else [content[:8], content[8:]]
    for index, part in enumerate(parts):
        delta: dict[str, Any] = {"content": part}
        if index == 0:
            delta["role"] = "assistant"
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": str(body.get("model") or "mock-model"),
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(_delay_seconds())

    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": str(body.get("model") or "mock-model"),
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": _usage(body, len(content)),
    }
    yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return {"calls": dict(CALL_COUNTS), "delay_ms": _delay_seconds() * 1000}


@app.get("/last-request")
async def last_request() -> dict[str, Any]:
    """Expose the latest request shape for local benchmark diagnostics."""
    return LAST_REQUEST


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": {"message": "request must be an object"}}, status_code=400)
    LAST_REQUEST.clear()
    LAST_REQUEST.update(body)

    kind = "stream" if body.get("stream") else "completion"
    if body.get("tools"):
        kind = "tool_call"
    elif body.get("response_format"):
        kind = "json_schema"
    CALL_COUNTS[kind] += 1
    await asyncio.sleep(_delay_seconds())

    if body.get("stream"):
        return StreamingResponse(_stream_response(body), media_type="text/event-stream")
    return JSONResponse(_completion_response(body))


__all__ = ["app"]
