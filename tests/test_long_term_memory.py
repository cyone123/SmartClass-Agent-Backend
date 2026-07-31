from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.base import SearchItem

from app.core import memory as memory_module
from app.core.graph import route_decision
from app.core.memory import (
    DEFAULT_USER_ID,
    apply_memory_tool_call,
    choose_relevant_experience_memories,
    delete_memory_item,
    experience_namespace,
    profile_namespace,
    put_memory_item,
    reflect_profile_memory,
    search_memory_items,
    should_reflect_profile_memory,
)
from app.schemas.chat import ChatRequest


class FakeStore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, ...], dict[str, dict[str, Any]]] = {}

    async def asearch(self, namespace_prefix, /, *, query=None, filter=None, limit=10, offset=0, refresh_ttl=None):
        _ = query, filter, refresh_ttl
        namespace = tuple(namespace_prefix)
        records = self.data.get(namespace, {})
        now = datetime.now(UTC)
        items = [
            SearchItem(
                namespace=namespace,
                key=key,
                value=value,
                created_at=now,
                updated_at=now,
            )
            for key, value in records.items()
        ]
        return items[offset : offset + limit]

    async def aget(self, namespace, key, *, refresh_ttl=None):
        _ = refresh_ttl
        namespace = tuple(namespace)
        value = self.data.get(namespace, {}).get(key)
        if value is None:
            return None
        now = datetime.now(UTC)
        return SearchItem(
            namespace=namespace,
            key=key,
            value=value,
            created_at=now,
            updated_at=now,
        )

    async def aput(self, namespace, key, value, index=None, *, ttl=None):
        _ = index, ttl
        self.data.setdefault(tuple(namespace), {})[key] = dict(value)

    async def adelete(self, namespace, key):
        self.data.get(tuple(namespace), {}).pop(key, None)


class FakeExperienceSelector:
    async def ainvoke(self, messages):
        _ = messages
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "select_experience_memories",
                    "args": {"memory_ids": ["exp-1", "missing", "exp-2", "exp-3"]},
                    "id": "selection-1",
                }
            ],
        )


class FakeProfileReflector:
    async def ainvoke(self, messages):
        _ = messages
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "create_memory",
                    "args": {
                        "title": "Answer style",
                        "summary": "Prefers concise answers",
                        "content": "The teacher prefers concise answers.",
                        "tags": ["style"],
                    },
                    "id": "memory-call-1",
                }
            ],
        )


def test_memory_namespaces_are_account_scoped() -> None:
    assert profile_namespace("teacher-1") == ("users", "teacher-1", "profile")
    assert experience_namespace("teacher-1") == ("users", "teacher-1", "experiences")
    assert profile_namespace("") == ("users", DEFAULT_USER_ID, "profile")


def test_memory_store_put_search_delete_round_trip() -> None:
    async def run() -> None:
        store = FakeStore()
        namespace = profile_namespace("teacher-1")
        created = await put_memory_item(
            store,
            namespace,
            value={
                "kind": "profile",
                "title": "Style",
                "summary": "Use concise answers",
                "content": "The teacher prefers concise answers.",
                "tags": ["style"],
            },
            key="memory-1",
        )
        assert created["id"] == "memory-1"

        items = await search_memory_items(store, namespace)
        assert len(items) == 1
        assert items[0]["title"] == "Style"

        await delete_memory_item(store, namespace, "memory-1")
        assert await search_memory_items(store, namespace) == []

    asyncio.run(run())


def test_experience_selection_loads_full_selected_memories(monkeypatch) -> None:
    async def run() -> None:
        store = FakeStore()
        namespace = experience_namespace("teacher-1")
        for memory_id in ("exp-1", "exp-2", "exp-3"):
            await put_memory_item(
                store,
                namespace,
                key=memory_id,
                value={
                    "kind": "experience",
                    "title": f"Experience {memory_id}",
                    "summary": f"Summary {memory_id}",
                    "content": f"Full reusable content {memory_id}",
                    "tags": [],
                },
            )

        monkeypatch.setattr(memory_module, "experience_selector", FakeExperienceSelector())
        context, selected = await choose_relevant_experience_memories(
            store=store,
            user_id="teacher-1",
            state={"messages": [HumanMessage(content="Need a lesson plan")]},
        )

        assert [item["id"] for item in selected] == ["exp-1", "exp-2", "exp-3"]
        assert "Full reusable content exp-1" in context

    asyncio.run(run())


def test_experience_selection_uses_exact_title_without_model(monkeypatch) -> None:
    async def run() -> None:
        store = FakeStore()
        namespace = experience_namespace("teacher-1")
        await put_memory_item(
            store,
            namespace,
            key="exp-quadratic",
            value={
                "kind": "experience",
                "title": "二次函数",
                "summary": "先画图，再解释函数性质",
                "content": "先画图，再解释函数性质",
                "tags": [],
            },
        )

        class UnexpectedSelector:
            async def ainvoke(self, prompt):
                raise AssertionError("exact title match should not invoke the model")

        monkeypatch.setattr(memory_module, "experience_selector", UnexpectedSelector())
        context, selected = await choose_relevant_experience_memories(
            store=store,
            user_id="teacher-1",
            state={"messages": [HumanMessage(content="设计一节二次函数课程")]},
        )

        assert [item["id"] for item in selected] == ["exp-quadratic"]
        assert "先画图" in context

    asyncio.run(run())


def test_profile_reflection_writes_memory_from_tool_call(monkeypatch) -> None:
    async def run() -> None:
        store = FakeStore()
        monkeypatch.setattr(memory_module, "profile_reflector", FakeProfileReflector())
        created = await reflect_profile_memory(
            store=store,
            user_id="teacher-1",
            state={"messages": [HumanMessage(content="Please remember I prefer concise answers.")]},
        )
        assert created is not None
        assert created["title"] == "Answer style"
        items = await search_memory_items(store, profile_namespace("teacher-1"))
        assert len(items) == 1
        assert items[0]["content"] == "The teacher prefers concise answers."

    asyncio.run(run())


def test_profile_reflection_eligibility_rejects_smalltalk_and_temporary_context() -> None:
    assert not should_reflect_profile_memory(
        {"messages": [HumanMessage(content="你好，今天天气真好")]}
    )
    assert not should_reflect_profile_memory(
        {"messages": [HumanMessage(content="我的班级来自某学校，请设计一节经济学课程")]}
    )
    assert should_reflect_profile_memory(
        {"messages": [HumanMessage(content="我偏好用案例分析法教学，请记住")]}
    )


def test_profile_reflection_skips_model_without_stable_signal(monkeypatch) -> None:
    async def run() -> None:
        store = FakeStore()

        class UnexpectedReflector:
            async def ainvoke(self, messages):
                raise AssertionError("smalltalk must not invoke profile reflection")

        monkeypatch.setattr(memory_module, "profile_reflector", UnexpectedReflector())
        created = await reflect_profile_memory(
            store=store,
            user_id="teacher-1",
            state={"messages": [HumanMessage(content="你好，今天天气真好")]},
        )

        assert created is None
        assert await search_memory_items(store, profile_namespace("teacher-1")) == []

    asyncio.run(run())


def test_memory_tool_call_redacts_named_school_and_socioeconomic_background() -> None:
    async def run() -> None:
        store = FakeStore()
        namespace = profile_namespace("teacher-1")
        created = await apply_memory_tool_call(
            store,
            namespace,
            {
                "name": "create_memory",
                "args": {
                    "title": "班级背景",
                    "summary": "北京市第一中学高三班，学生均来自富裕家庭",
                    "content": "教师在北京市第一中学任教，学生均来自富裕家庭。",
                    "tags": ["北京市第一中学"],
                },
            },
            kind="profile",
            source_thread_id=None,
            source_plan_id=None,
        )

        serialized = str(created)
        assert "北京市第一中学" not in serialized
        assert "富裕家庭" not in serialized
        assert "某学校" in serialized
        assert "不同家庭背景" in serialized

    asyncio.run(run())


def test_route_decision_targets_performance_fast_paths() -> None:
    assert route_decision({"intent": "normal_chat"}) == "normal_chat_memory_retrieval_node"
    assert route_decision({"intent": "teaching_plan"}) == "teaching_plan_memory_retrieval_node"
    assert route_decision({"intent": "artifact_revision"}) == "artifact_revision_memory_retrieval_node"


def test_chat_request_ignores_client_supplied_user_id() -> None:
    payload = ChatRequest.model_validate({"message": "hello", "user_id": "spoofed-user"})
    assert not hasattr(payload, "user_id")
