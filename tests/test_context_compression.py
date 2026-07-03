from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage

from app.core.context_compression import (
    COMPRESSED_CONTEXT_MARKER,
    CompressionSettings,
    build_compression_plan,
    build_replacement_update,
    build_structured_state_preface,
    compress_state_messages,
    estimate_message_tokens,
    is_compressed_context_message,
)
from app.core.observability import (
    ObservationEvent,
    RunContext,
    assert_prometheus_labels_are_bounded,
    sanitize_observation_fields,
)


class MemorySink:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def emit(self, event: ObservationEvent) -> None:
        self.events.append(event)


class FakeCompressionModel:
    model_name = "fake-compressor"
    request_timeout = 5

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def get_num_tokens_from_messages(self, messages: list[Any]) -> int:
        return max(100, len(messages) * 100)

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        if self.fail:
            raise RuntimeError("compression unavailable")
        assert any("Conversation to compress" in str(message.content) for message in messages)
        return AIMessage(content="已确认目标：设计勾股定理课程。保留约束：适合初中。")


def _thread_messages(turns: int = 5) -> list[Any]:
    messages: list[Any] = []
    for index in range(turns):
        messages.append(HumanMessage(id=f"h-{index}", content=f"第 {index} 轮：设计初中数学勾股定理课程"))
        messages.append(AIMessage(id=f"a-{index}", content=f"第 {index} 轮回复：已记录课程要求"))
    return messages


def _settings(**overrides: Any) -> CompressionSettings:
    values = {
        "enabled": True,
        "trigger_tokens": 10,
        "keep_recent_turns": 2,
        "max_output_tokens": 256,
        "max_preface_chars": 2000,
    }
    values.update(overrides)
    return CompressionSettings(**values)


def test_compression_plan_keeps_recent_turns() -> None:
    state = {"messages": _thread_messages(5)}
    plan = build_compression_plan(
        state,
        settings=_settings(),
        model=FakeCompressionModel(),
    )

    assert plan.should_compress is True
    assert plan.reason == "threshold_reached"
    assert plan.compressible_message_count == 6
    assert plan.retained_message_count == 4
    assert [message.id for message in plan.retained_messages] == ["h-3", "a-3", "h-4", "a-4"]


def test_compression_plan_skips_when_ids_are_missing() -> None:
    messages = _thread_messages(4)
    messages[0].id = None
    plan = build_compression_plan(
        {"messages": messages},
        settings=_settings(),
        model=FakeCompressionModel(),
    )

    assert plan.should_compress is False
    assert plan.reason == "missing_message_ids"


def test_token_estimation_uses_provider_counter_and_fallback() -> None:
    messages = [HumanMessage(content="abcd" * 20)]

    assert estimate_message_tokens(messages, model=FakeCompressionModel()) == 100
    assert estimate_message_tokens(messages, model=None) >= 20


def test_structured_state_preface_includes_authoritative_fields() -> None:
    preface = build_structured_state_preface(
        {
            "teaching_metadata": {"subject": "数学", "grade": "初中", "topic": "勾股定理"},
            "rag_context": "教材指出勾股定理需要结合直角三角形情境。",
            "artifact_catalog": [{"id": 7, "type": "ppt", "title": "勾股定理课件"}],
            "revision_results": [{"artifact_id": 8, "status": "ready"}],
        },
        max_chars=2000,
    )

    assert "Teaching metadata" in preface
    assert "勾股定理" in preface
    assert "RAG digest" in preface
    assert "Artifact state" in preface
    assert "Revision state" in preface


def test_repeated_compression_replaces_prior_compressed_context() -> None:
    messages = [
        SystemMessage(
            id="old-compressed",
            content=f"{COMPRESSED_CONTEXT_MARKER}\n旧摘要",
            additional_kwargs={"smartclass_context_compressed": True},
        ),
        *_thread_messages(5),
    ]
    plan = build_compression_plan(
        {"messages": messages},
        settings=_settings(),
        model=FakeCompressionModel(),
    )
    compressed = SystemMessage(
        id="new-compressed",
        content=f"{COMPRESSED_CONTEXT_MARKER}\n新摘要",
        additional_kwargs={"smartclass_context_compressed": True},
    )
    update = build_replacement_update(messages, compressed, plan.retained_messages)
    added_messages = update["messages"][len(messages) :]

    assert plan.should_compress is True
    assert any(message.id == "old-compressed" for message in plan.compressible_messages)
    assert [message.id for message in added_messages if is_compressed_context_message(message)] == [
        "new-compressed"
    ]


def test_replacement_update_deletes_all_messages_then_adds_summary_first() -> None:
    messages = _thread_messages(3)
    retained = messages[-2:]
    compressed = SystemMessage(
        id="compressed-1",
        content=f"{COMPRESSED_CONTEXT_MARKER}\nsummary",
        additional_kwargs={"smartclass_context_compressed": True},
    )
    update = build_replacement_update(messages, compressed, retained)

    assert all(isinstance(message, RemoveMessage) for message in update["messages"][: len(messages)])
    assert update["messages"][len(messages)] is compressed
    assert update["messages"][len(messages) + 1 :] == retained
    assert is_compressed_context_message(compressed)


def test_compress_state_messages_skip_observations_are_bounded() -> None:
    async def run() -> None:
        sink = MemorySink()
        result = await compress_state_messages(
            {"messages": _thread_messages(2)},
            context=RunContext(run_id="run-1", thread_id="thread-1", user_id="2"),
            sink=sink,
            settings=_settings(enabled=False),
            model=FakeCompressionModel(),
        )

        assert result.status == "skipped"
        assert result.reason == "disabled"
        skipped = [event for event in sink.events if event.event == "context.compression.skipped"]
        assert skipped
        assert skipped[-1].fields["decision"] == "skip"
        assert "messages" not in skipped[-1].fields
        assert "summary" not in skipped[-1].fields

    asyncio.run(run())


def test_compress_state_messages_success_emits_observations_and_preserves_state() -> None:
    async def run() -> None:
        sink = MemorySink()
        state = {
            "messages": _thread_messages(5),
            "teaching_metadata": {"subject": "数学", "grade": "初中", "topic": "勾股定理"},
            "rag_context": "教材 RAG 内容摘要",
        }
        result = await compress_state_messages(
            state,
            context=RunContext(run_id="run-1", thread_id="thread-1", user_id="2"),
            sink=sink,
            settings=_settings(),
            model=FakeCompressionModel(),
        )

        assert result.status == "success"
        assert result.update is not None
        compressed = next(
            message for message in result.update["messages"] if is_compressed_context_message(message)
        )
        assert COMPRESSED_CONTEXT_MARKER in compressed.content
        assert "Teaching metadata" in compressed.content
        assert state["teaching_metadata"]["topic"] == "勾股定理"
        assert {event.event for event in sink.events} >= {
            "context.compression.checked",
            "context.compression.started",
            "context.compression.completed",
            "llm.call",
        }

    asyncio.run(run())


def test_context_compression_observation_redacts_sensitive_values() -> None:
    fields = sanitize_observation_fields(
        {
            "error_message": (
                "failed for Bearer abc.def.ghi at "
                "https://example.test/download?access_token=secret&X-Amz-Signature=sig "
                "D:\\Learn\\langchain\\demo\\backend\\storage\\file.docx"
            ),
            "summary_size": 1200,
        }
    )

    error_message = fields["error_message"]
    assert "Bearer [REDACTED]" in error_message
    assert "access_token=%5BREDACTED%5D" in error_message
    assert "X-Amz-Signature=%5BREDACTED%5D" in error_message
    assert "[REDACTED_PATH]" in error_message
    assert fields["summary_size"] == 1200


def test_compress_state_messages_failure_is_non_destructive() -> None:
    async def run() -> None:
        sink = MemorySink()
        messages = _thread_messages(5)
        result = await compress_state_messages(
            {"messages": messages},
            context=RunContext(run_id="run-1", thread_id="thread-1", user_id="2"),
            sink=sink,
            settings=_settings(),
            model=FakeCompressionModel(fail=True),
        )

        assert result.status == "failed"
        assert result.update is None
        assert messages[0].content.startswith("第 0 轮")
        failed = [event for event in sink.events if event.event == "context.compression.failed"]
        assert failed
        assert failed[-1].fields["error_category"] == "unknown"

    asyncio.run(run())


def test_context_compression_prometheus_labels_stay_bounded() -> None:
    event = ObservationEvent(
        event="context.compression.completed",
        kind="log",
        context=RunContext(run_id="run-1", thread_id="thread-1", plan_id=1, user_id="2"),
        status="success",
        fields={
            "estimated_tokens_before": 30000,
            "estimated_tokens_after": 8000,
            "summary_size": 1200,
            "reason": "threshold_reached",
        },
    )

    assert_prometheus_labels_are_bounded(event)
