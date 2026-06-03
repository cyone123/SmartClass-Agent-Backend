from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.api.chat import router as chat_router
from app.core.agent import LLMObservationMiddleware, get_agent_runtime
from app.core.llm import get_model
from app.core.auth import get_current_user
from app.core.observability import (
    JsonlTraceSink,
    ObservationEvent,
    RunContext,
    extract_token_usage,
    observe_llm_call,
    sanitize_observation_fields,
    trace_span,
)
from app.core.workspace import (
    LocalSubprocessExecutionBackend,
    WorkspaceManager,
    WorkspaceValidationError,
)
from app.dependencies.db import get_db


class MemoryObservationSink:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def emit(self, event: ObservationEvent) -> None:
        self.events.append(event)


class StructuredDecision(BaseModel):
    intent: str
    needs_clarification: bool = False


def test_observability_sanitizes_sensitive_fields() -> None:
    fields = sanitize_observation_fields(
        {
            "authorization": "Bearer secret-token",
            "api_key": "sk-secret",
            "password": "pw",
            "url": "https://minio.example/file?X-Amz-Credential=abc&X-Amz-Signature=def&safe=1",
            "jwt": "eyJabc.def.ghi",
            "path": r"D:\Learn\langchain\demo\backend\.env",
            "long": "x" * 1200,
        }
    )

    assert fields["authorization"] == "[REDACTED]"
    assert fields["api_key"] == "[REDACTED]"
    assert fields["password"] == "[REDACTED]"
    assert "X-Amz-Credential=%5BREDACTED%5D" in fields["url"]
    assert fields["jwt"] == "[REDACTED]"
    assert "[REDACTED_PATH]" in fields["path"]
    assert fields["long"].endswith("...[truncated]")


def test_observability_sanitizes_structured_objects_to_json_safe_values() -> None:
    fields = sanitize_observation_fields(
        {
            "decision": StructuredDecision(intent="teaching_plan"),
            "nested": {"result": StructuredDecision(intent="normal_chat")},
        }
    )

    assert fields["decision"] == {"intent": "teaching_plan", "needs_clarification": False}
    assert fields["nested"]["result"]["intent"] == "normal_chat"
    json.dumps(fields, ensure_ascii=False)


def test_trace_span_emits_success_and_failed_events() -> None:
    sink = MemoryObservationSink()
    context = RunContext(run_id="run-1", thread_id="thread-1", plan_id=1, user_id="2")

    with trace_span("test.span", context=context, sink=sink, fields={"input_size": 3}) as fields:
        fields["output_size"] = 5

    try:
        with trace_span("test.failed", context=context, sink=sink):
            raise TimeoutError("Bearer should-redact")
    except TimeoutError:
        pass

    assert [event.status for event in sink.events] == ["running", "success", "running", "failed"]
    success = sink.events[1]
    failed = sink.events[3]
    assert success.duration_ms is not None
    assert success.fields["output_size"] == 5
    assert failed.fields["error_category"] == "timeout"
    assert "should-redact" not in failed.fields["error_message"]


def test_llm_usage_metadata_is_recorded_when_available() -> None:
    usage_message = AIMessage(content="ok")
    usage_message.usage_metadata = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
    assert extract_token_usage(usage_message) == {
        "token_usage_available": True,
        "input_tokens": 10,
        "output_tokens": 3,
        "total_tokens": 13,
    }

    response_metadata_message = AIMessage(
        content="ok",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 10,
            }
        },
    )
    assert extract_token_usage(response_metadata_message) == {
        "token_usage_available": True,
        "input_tokens": 8,
        "output_tokens": 2,
        "total_tokens": 10,
    }

    response_usage_message = AIMessage(
        content="ok",
        response_metadata={
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 4,
                "total_tokens": 11,
            }
        },
    )
    assert extract_token_usage(response_usage_message) == {
        "token_usage_available": True,
        "input_tokens": 7,
        "output_tokens": 4,
        "total_tokens": 11,
    }

    structured_raw_message = AIMessage(content="ok")
    structured_raw_message.usage_metadata = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
    assert extract_token_usage({"parsed": {"ok": True}, "raw": structured_raw_message}) == {
        "token_usage_available": True,
        "input_tokens": 12,
        "output_tokens": 5,
        "total_tokens": 17,
    }

    response_result_message = AIMessage(content="ok")
    response_result_message.usage_metadata = {"input_tokens": 6, "output_tokens": 2, "total_tokens": 8}
    assert extract_token_usage(ModelResponse(result=[response_result_message])) == {
        "token_usage_available": True,
        "input_tokens": 6,
        "output_tokens": 2,
        "total_tokens": 8,
    }

    assert extract_token_usage(AIMessage(content="ok")) == {"token_usage_available": False}


def test_observe_llm_call_records_token_usage() -> None:
    sink = MemoryObservationSink()
    message = HumanMessage(content="hello")
    response = AIMessage(content="ok")
    response.usage_metadata = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}

    async def run() -> AIMessage:
        return await observe_llm_call(
            "llm.call",
            lambda: asyncio.sleep(0, result=response),
            context=RunContext(run_id="run-1", thread_id="thread-1", user_id="2"),
            sink=sink,
            model=SimpleNamespace(model_name="fake-model"),
            messages=[message],
            fields={"node": "normal_chat_node"},
        )

    assert asyncio.run(run()) is response
    event = next(event for event in sink.events if event.event == "llm.call")
    assert event.status == "success"
    assert event.fields["model"] == "fake-model"
    assert event.fields["node"] == "normal_chat_node"
    assert event.fields["token_usage_available"] is True
    assert event.fields["input_tokens"] == 5
    assert event.fields["output_tokens"] == 2
    assert event.fields["total_tokens"] == 7


def test_streaming_models_request_usage_metadata() -> None:
    model = get_model(streaming=True)

    assert model.streaming is True
    assert model.stream_usage is True


def test_jsonl_trace_truncation_keeps_valid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OBSERVABILITY_MAX_JSONL_BYTES_PER_EVENT", "400")
    sink = JsonlTraceSink(trace_dir=tmp_path)

    sink.emit(
        ObservationEvent(
            event="huge.event",
            kind="metric",
            context=RunContext(run_id="run-1", thread_id="thread-1", plan_id=1, user_id="2"),
            status="success",
            fields={"large": "x" * 10000, "safe": "ok"},
        )
    )

    [path] = list(tmp_path.glob("*.jsonl"))
    line = path.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["event"] == "huge.event"
    assert payload["jsonl_truncated"] is True


def test_workspace_execution_records_observation_event(tmp_path: Path) -> None:
    sink = MemoryObservationSink()
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "plan_id": 1,
            "user_id": "2",
            "observation_sink": sink,
        }
    }
    manager = WorkspaceManager(backend=LocalSubprocessExecutionBackend(timeout_seconds=5))
    paths = tmp_path / "hello.py"
    paths.write_text("print('hello')\n", encoding="utf-8")

    # Put the file through the public workspace write path so path policy remains covered.
    manager.write_file(config, relative_path="hello.py", content="print('hello')\n", overwrite=True)
    result = manager.run_code(config, language="python", entrypoint="hello.py")

    assert result.exit_code == 0
    event = next(event for event in sink.events if event.event == "workspace.code_execution")
    assert event.status == "success"
    assert event.fields["stdout_size"] == len(result.stdout)
    assert "stdout" not in event.fields
    assert event.fields["entrypoint"] == "hello.py"


def test_workspace_validation_failure_records_observation_event() -> None:
    sink = MemoryObservationSink()
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "plan_id": 1,
            "user_id": "2",
            "observation_sink": sink,
        }
    }
    manager = WorkspaceManager(backend=LocalSubprocessExecutionBackend(timeout_seconds=5))

    with pytest.raises(WorkspaceValidationError):
        manager.run_code(config, language="ruby", entrypoint="missing.rb")

    event = next(event for event in sink.events if event.event == "workspace.code_execution")
    assert event.status == "failed"
    assert event.fields["validation_phase"] is True
    assert event.fields["error_category"] == "validation_error"
    assert event.fields["language"] == "ruby"


def test_llm_observation_middleware_records_tool_duration() -> None:
    sink = MemoryObservationSink()
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "plan_id": 1,
            "user_id": "2",
            "observation_sink": sink,
        }
    }
    request = SimpleNamespace(
        runtime=SimpleNamespace(config=config),
        tool_call={"name": "run_skill_script", "args": {"skill_name": "pdf"}},
    )
    middleware = LLMObservationMiddleware(agent_name="attachment_skill_agent")

    response = middleware.wrap_tool_call(request, lambda _: {"ok": True})

    assert response == {"ok": True}
    event = next(event for event in sink.events if event.event == "tool.invoke")
    assert event.status == "success"
    assert event.duration_ms is not None
    assert event.fields["agent_name"] == "attachment_skill_agent"
    assert event.fields["tool_name"] == "run_skill_script"


def test_llm_observation_middleware_records_model_token_usage_and_context() -> None:
    sink = MemoryObservationSink()
    request = SimpleNamespace(
        state={
            "messages": [HumanMessage(content="hello")],
            "configurable": {
                "thread_id": "thread-1",
                "run_id": "run-1",
                "plan_id": 1,
                "user_id": "2",
                "observation_sink": sink,
            },
        },
        model=SimpleNamespace(model_name="fake-model"),
    )
    response_message = AIMessage(content="ok")
    response_message.usage_metadata = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
    middleware = LLMObservationMiddleware(agent_name="attachment_skill_agent")

    response = middleware.wrap_model_call(
        request,
        lambda _: ModelResponse(result=[response_message]),
    )

    assert response.result == [response_message]
    event = next(event for event in sink.events if event.event == "llm.call")
    assert event.status == "success"
    assert event.context.run_id == "run-1"
    assert event.context.thread_id == "thread-1"
    assert event.fields["agent_name"] == "attachment_skill_agent"
    assert event.fields["model"] == "fake-model"
    assert event.fields["token_usage_available"] is True
    assert event.fields["input_tokens"] == 10
    assert event.fields["output_tokens"] == 3
    assert event.fields["total_tokens"] == 13


def test_chat_stream_passes_run_context_to_agent_runtime() -> None:
    captured: dict[str, object] = {}

    class FakeAgentRuntime:
        async def stream_agent_events(self, *args, **kwargs):
            _ = args
            captured.update(kwargs)
            yield {"event": "token", "data": {"run_id": kwargs["run_id"], "text": "ok"}}

    async def run() -> None:
        app = FastAPI()
        app.include_router(chat_router)

        async def override_db():
            yield None

        async def override_agent_runtime():
            return FakeAgentRuntime()

        async def override_current_user():
            return SimpleNamespace(id=7)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_agent_runtime] = override_agent_runtime
        app.dependency_overrides[get_current_user] = override_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/chat/stream", json={"message": "hello"})

        assert response.status_code == 200
        assert "event: metadata" in response.text
        assert "event: token" in response.text

    asyncio.run(run())

    run_context = captured["run_context"]
    assert isinstance(run_context, RunContext)
    assert run_context.user_id == "7"
    assert captured["user_id"] == "7"
    assert captured["observation_sink"] is not None
