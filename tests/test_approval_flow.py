from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core import graph as graph_module
from app.core.agent import AgentRuntime
from app.core.graph import (
    METADATA_REVIEW_INTERRUPT_NODE,
    metadata_completion_condition,
    metadata_review_interrupt_node,
    teaching_plan_review_interrupt_node,
)
from app.services import session_service


@dataclass
class FakeInterrupt:
    id: str
    value: dict


@dataclass
class FakeStateSnapshot:
    values: dict
    interrupts: tuple[FakeInterrupt, ...] = ()
    next: tuple[str, ...] = ()


class FakeGraph:
    def __init__(self, snapshots: list[FakeStateSnapshot]) -> None:
        self._snapshots = snapshots
        self._index = 0

    async def aget_state(self, config):
        _ = config
        index = min(self._index, len(self._snapshots) - 1)
        snapshot = self._snapshots[index]
        self._index += 1
        return snapshot

    async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=None, version=None):
        _ = graph_input, config, stream_mode, subgraphs, version
        if False:
            yield None


def _build_runtime(fake_graph: FakeGraph) -> AgentRuntime:
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.streaming_graph = fake_graph
    runtime.graph = fake_graph
    runtime._thread_locks = {}
    runtime._thread_locks_guard = asyncio.Lock()

    async def _analyze_attachments(*args, **kwargs):
        _ = args, kwargs
        return None

    async def _generate_follow_up_suggestions(*args, **kwargs):
        raise AssertionError("suggestions should not be generated while an approval is pending")

    runtime.analyze_attachments = _analyze_attachments
    runtime._generate_follow_up_suggestions = _generate_follow_up_suggestions
    return runtime


def test_metadata_completion_condition_routes_to_metadata_review() -> None:
    state = {
        "teaching_metadata": {
            "subject": "physics",
            "grade": "high school",
            "topic": "Newton",
            "course_duration": "45m",
            "core_points": ["law"],
            "key_points": ["concept"],
            "difficult_points": ["inertia"],
            "teaching_objectives": "Understand the first law",
            "is_complete": True,
        }
    }
    assert metadata_completion_condition(state) == METADATA_REVIEW_INTERRUPT_NODE


def test_metadata_review_interrupt_node_routes_by_resume_payload(monkeypatch) -> None:
    state = {
        "messages": [HumanMessage(content="help me")],
        "teaching_metadata": {
            "subject": "physics",
            "grade": "high school",
            "topic": "Newton",
            "course_duration": "45m",
            "core_points": ["law"],
            "key_points": ["concept"],
            "difficult_points": ["inertia"],
            "teaching_objectives": "Understand the first law",
            "is_complete": True,
        },
    }

    monkeypatch.setattr(
        graph_module,
        "interrupt",
        lambda payload: {"action": "approve", "interrupt_id": "approval-1"},
    )
    approve_result = metadata_review_interrupt_node(state)
    assert approve_result.goto == "rag_retrieval_node"

    monkeypatch.setattr(
        graph_module,
        "interrupt",
        lambda payload: {"message": "补充目标", "attachment_text": "summary"},
    )
    modify_result = metadata_review_interrupt_node(state)
    assert modify_result.goto == "metadata_structer_node"
    assert modify_result.update["messages"][-1].content == "补充目标"


def test_teaching_plan_review_interrupt_node_routes_by_resume_payload(monkeypatch) -> None:
    state = {
        "messages": [HumanMessage(content="生成方案")],
        "teaching_design_plan": "Plan body",
    }

    monkeypatch.setattr(
        graph_module,
        "interrupt",
        lambda payload: {"action": "approve", "interrupt_id": "approval-2"},
    )
    approve_result = teaching_plan_review_interrupt_node(state)
    assert list(approve_result.goto) == [
        "ppt_generate_node",
        "docx_generate_node",
        "html_game_generate_node",
    ]

    monkeypatch.setattr(
        graph_module,
        "interrupt",
        lambda payload: {"message": "请缩短导入环节"},
    )
    modify_result = teaching_plan_review_interrupt_node(state)
    assert modify_result.goto == "teaching_design_planner"
    assert modify_result.update["messages"][-1].content == "请缩短导入环节"


def test_validate_approval_request_rejects_stale_interrupt_id() -> None:
    approval_payload = {
        "stage": "metadata_review",
        "title": "确认结构化教学要素",
        "description": "desc",
        "confirm_label": "确认并继续",
        "cancel_label": "取消并修改",
    }
    runtime = _build_runtime(
        FakeGraph(
            [
                FakeStateSnapshot(
                    values={},
                    interrupts=(FakeInterrupt(id="real-interrupt", value=approval_payload),),
                    next=("metadata_review_interrupt_node",),
                )
            ]
        )
    )

    async def run() -> None:
        with pytest.raises(ValueError, match="stale"):
            await runtime.validate_approval_request("thread-1", "stale-interrupt")

    asyncio.run(run())


def test_stream_agent_events_emits_approval_without_suggestions() -> None:
    approval_payload = {
        "stage": "metadata_review",
        "title": "确认结构化教学要素",
        "description": "desc",
        "confirm_label": "确认并继续",
        "cancel_label": "取消并修改",
        "metadata": {"subject": "physics"},
    }
    runtime = _build_runtime(
        FakeGraph(
            [
                FakeStateSnapshot(values={}, interrupts=(), next=()),
                FakeStateSnapshot(
                    values={},
                    interrupts=(FakeInterrupt(id="approval-1", value=approval_payload),),
                    next=("metadata_review_interrupt_node",),
                ),
            ]
        )
    )

    async def run() -> None:
        events = [
            event
            async for event in runtime.stream_agent_events(
                "请帮我备课",
                "thread-1",
                run_id="run-1",
            )
        ]
        approval_events = [event for event in events if event["event"] == "approval"]
        assert len(approval_events) == 1
        assert approval_events[0]["data"]["interrupt_id"] == "approval-1"
        assert approval_events[0]["data"]["run_id"] == "run-1"
        assert not any(event["event"] == "suggestions" for event in events)

    asyncio.run(run())


def test_session_history_appends_pending_approval_card() -> None:
    snapshot = FakeStateSnapshot(
        values={
            "messages": [
                HumanMessage(content="请生成教学计划"),
                AIMessage(content="好的，我先整理教学要素。"),
            ]
        }
    )

    class FakeHistoryGraph:
        async def aget_state(self, config):
            _ = config
            return snapshot

    class FakeAgentRuntime:
        def __init__(self) -> None:
            self.graph = FakeHistoryGraph()

        async def get_pending_approval(self, thread_id):
            _ = thread_id
            return {
                "interrupt_id": "approval-3",
                "stage": "metadata_review",
                "title": "确认结构化教学要素",
                "description": "desc",
                "confirm_label": "确认并继续",
                "cancel_label": "取消并修改",
                "metadata": {"subject": "physics"},
            }

    async def run() -> None:
        messages = await session_service.get_message_histry("thread-1", FakeAgentRuntime())
        assert messages[-1]["type"] == "approval-card"
        assert messages[-1]["approval"]["interrupt_id"] == "approval-3"

    asyncio.run(run())
