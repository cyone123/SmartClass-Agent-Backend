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
    choose_relevant_experience_memories,
    delete_memory_item,
    experience_namespace,
    reflect_profile_memory,
    profile_namespace,
    put_memory_item,
    search_memory_items,
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


def test_profile_reflection_writes_memory_from_tool_call(monkeypatch) -> None:
    async def run() -> None:
        store = FakeStore()
        monkeypatch.setattr(memory_module, "profile_reflector", FakeProfileReflector())
        created = await reflect_profile_memory(
            store=store,
            user_id="teacher-1",
            state={
                "messages": [
                    HumanMessage(content="Please remember I prefer concise answers.")
                ]
            },
        )
        assert created is not None
        assert created["title"] == "Answer style"
        items = await search_memory_items(store, profile_namespace("teacher-1"))
        assert len(items) == 1
        assert items[0]["content"] == "The teacher prefers concise answers."

    asyncio.run(run())


def test_route_decision_targets_memory_retrieval_nodes() -> None:
    assert route_decision({"intent": "normal_chat"}) == "normal_chat_memory_retrieval_node"
    assert route_decision({"intent": "teaching_plan"}) == "teaching_plan_memory_retrieval_node"
    assert route_decision({"intent": "artifact_revision"}) == "artifact_revision_memory_retrieval_node"


def test_chat_request_defaults_user_id() -> None:
    payload = ChatRequest.model_validate({"message": "hello"})
    assert payload.user_id == DEFAULT_USER_ID
