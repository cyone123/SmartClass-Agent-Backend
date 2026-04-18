from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core import graph as graph_module


@dataclass
class FakeModel:
    model_name: str
    openai_api_base: str


class FakeRunnable:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[list[object], dict]] = []

    def invoke(self, messages, **kwargs):
        materialized_messages = list(messages)
        self.calls.append((materialized_messages, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def test_build_metadata_extraction_messages_limits_context_to_recent_human_turns() -> None:
    state = {
        "messages": [
            HumanMessage(content="第一次提供学科信息"),
            AIMessage(content="好的，我继续收集"),
            HumanMessage(content="第二次补充授课年级"),
            HumanMessage(content="第三次补充课程时长和目标"),
        ],
        "teaching_metadata": {
            "subject": "physics",
            "grade": None,
            "topic": None,
            "course_duration": "",
            "core_points": None,
            "key_points": None,
            "difficult_points": None,
            "teaching_objectives": None,
            "is_complete": False,
        },
    }

    messages = graph_module.build_metadata_extraction_messages(state)

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    prompt_text = messages[1].content
    assert "第一次提供学科信息" not in prompt_text
    assert "第二次补充授课年级" in prompt_text
    assert "第三次补充课程时长和目标" in prompt_text


def test_metadata_structer_node_uses_fast_model_without_fallback(monkeypatch) -> None:
    fast_runnable = FakeRunnable(
        response={
            "subject": "physics",
            "grade": "grade 8",
            "topic": "Newton's first law",
            "course_duration": "40 minutes",
            "core_points": ["inertia"],
            "key_points": ["state change"],
            "difficult_points": ["force misconception"],
            "teaching_objectives": "Students understand inertia.",
            "is_complete": True,
        }
    )
    fallback_runnable = FakeRunnable(error=AssertionError("fallback should not be called"))

    monkeypatch.setattr(graph_module, "metadata_extractor", fast_runnable)
    monkeypatch.setattr(graph_module, "metadata_extractor_fallback", fallback_runnable)
    monkeypatch.setattr(graph_module, "structured_fast_llm", FakeModel("fast-model", "https://fast.example.com/v1"))
    monkeypatch.setattr(graph_module, "structured_output_llm", FakeModel("fallback-model", "https://fallback.example.com/v1"))
    monkeypatch.setattr(graph_module, "is_structured_fallback_enabled", lambda: True)
    graph_module.STRUCTURED_SCHEMA_CALL_COUNTS.clear()

    state = {
        "messages": [HumanMessage(content="帮我准备一节初中物理牛顿第一定律课程，40分钟。")],
        "teaching_metadata": None,
    }

    result = graph_module.metadata_structer_node(state)

    assert result["teaching_metadata"]["topic"] == "Newton's first law"
    assert len(fast_runnable.calls) == 1
    assert len(fallback_runnable.calls) == 0


def test_metadata_structer_node_falls_back_when_fast_model_fails(monkeypatch) -> None:
    fast_runnable = FakeRunnable(error=RuntimeError("fast model timeout"))
    fallback_runnable = FakeRunnable(
        response={
            "subject": "physics",
            "grade": "grade 8",
            "topic": "Newton's first law",
            "course_duration": "40 minutes",
            "core_points": ["inertia"],
            "key_points": ["state change"],
            "difficult_points": ["force misconception"],
            "teaching_objectives": "Students understand inertia.",
            "is_complete": False,
        }
    )

    monkeypatch.setattr(graph_module, "metadata_extractor", fast_runnable)
    monkeypatch.setattr(graph_module, "metadata_extractor_fallback", fallback_runnable)
    monkeypatch.setattr(graph_module, "structured_fast_llm", FakeModel("fast-model", "https://fast.example.com/v1"))
    monkeypatch.setattr(graph_module, "structured_output_llm", FakeModel("fallback-model", "https://fallback.example.com/v1"))
    monkeypatch.setattr(graph_module, "is_structured_fallback_enabled", lambda: True)
    graph_module.STRUCTURED_SCHEMA_CALL_COUNTS.clear()

    state = {
        "messages": [
            HumanMessage(content="我要上一节牛顿第一定律课"),
            HumanMessage(content="授课对象是八年级，40分钟"),
        ],
        "teaching_metadata": {"subject": "physics", "is_complete": False},
    }

    result = graph_module.metadata_structer_node(state)

    assert result["teaching_metadata"]["grade"] == "grade 8"
    assert len(fast_runnable.calls) == 1
    assert len(fallback_runnable.calls) == 1


def test_intent_router_node_falls_back_to_reliable_model(monkeypatch) -> None:
    fast_router = FakeRunnable(error=RuntimeError("fast router parse failure"))
    fallback_router = FakeRunnable(
        response=graph_module.ConversationRoute(intent="teaching_plan", artifact_targets=[], needs_clarification=False)
    )

    monkeypatch.setattr(graph_module, "router", fast_router)
    monkeypatch.setattr(graph_module, "router_fallback", fallback_router)
    monkeypatch.setattr(graph_module, "structured_fast_llm", FakeModel("fast-model", "https://fast.example.com/v1"))
    monkeypatch.setattr(graph_module, "structured_output_llm", FakeModel("fallback-model", "https://fallback.example.com/v1"))
    monkeypatch.setattr(graph_module, "is_structured_fallback_enabled", lambda: True)
    graph_module.STRUCTURED_SCHEMA_CALL_COUNTS.clear()

    state = {
        "messages": [HumanMessage(content="请帮我设计一节初中物理教学方案")],
        "artifact_catalog": [],
    }

    result = graph_module.intent_router_node(state)

    assert result == {"intent": "teaching_plan"}
    assert len(fast_router.calls) == 1
    assert len(fallback_router.calls) == 1
