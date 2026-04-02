from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.core.graph import build_agent_graph
from app.core.rag import RagRuntime
from app.dependencies.db import close_agent_checkpointer, init_agent_checkpointer

INTERRUPT_FOR_USERINPUT_NODE = "interrupt_for_userinput"


def get_thread_config(thread_id: str) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }


def _message_to_text(message: AnyMessage) -> str:
    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "".join(text_parts)

    return str(content)


def get_final_response_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _message_to_text(message).strip()
    return ""


class AgentRuntime:
    def __init__(
        self,
        checkpointer: AsyncPostgresSaver,
        rag_runtime: RagRuntime,
    ) -> None:
        self.checkpointer = checkpointer
        self.rag_runtime = rag_runtime
        self.graph = build_agent_graph(
            checkpointer=checkpointer,
            rag_runtime=rag_runtime,
        )
        self.streaming_graph = build_agent_graph(
            streaming=True,
            checkpointer=checkpointer,
            rag_runtime=rag_runtime,
        )
        self._thread_locks: dict[str, asyncio.Lock] = {}
        self._thread_locks_guard = asyncio.Lock()

    async def _get_thread_lock(self, thread_id: str) -> asyncio.Lock:
        async with self._thread_locks_guard:
            lock = self._thread_locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._thread_locks[thread_id] = lock
            return lock

    async def _should_resume_thread(self, thread_id: str) -> bool:
        state_snapshot = await self.graph.aget_state(get_thread_config(thread_id))
        interrupts = getattr(state_snapshot, "interrupts", ()) or ()
        next_nodes = tuple(getattr(state_snapshot, "next", ()) or ())
        return bool(interrupts) and INTERRUPT_FOR_USERINPUT_NODE in next_nodes

    async def _get_graph_input(self, message: str, thread_id: str):
        return await self._get_graph_input_with_plan(message, thread_id, plan_id=None)

    async def _get_graph_input_with_plan(
        self,
        message: str,
        thread_id: str,
        *,
        plan_id: int | None,
    ):
        if await self._should_resume_thread(thread_id):
            return Command(resume=message)
        graph_input = {"messages": [HumanMessage(content=message)]}
        if plan_id is not None:
            graph_input["plan_id"] = plan_id
        return graph_input

    async def invoke_agent(
        self,
        message: str,
        thread_id: str,
        *,
        plan_id: int | None = None,
    ) -> str:
        lock = await self._get_thread_lock(thread_id)
        async with lock:
            graph_input = await self._get_graph_input_with_plan(
                message,
                thread_id,
                plan_id=plan_id,
            )
            result = await self.graph.ainvoke(
                graph_input,
                config=get_thread_config(thread_id),
            )
        return get_final_response_text(result["messages"])

    async def stream_agent_response(
        self,
        message: str,
        thread_id: str,
        *,
        plan_id: int | None = None,
    ) -> AsyncIterator[str]:
        lock = await self._get_thread_lock(thread_id)
        async with lock:
            graph_input = await self._get_graph_input_with_plan(
                message,
                thread_id,
                plan_id=plan_id,
            )
            async for chunk, metadata in self.streaming_graph.astream(
                graph_input,
                config=get_thread_config(thread_id),
                stream_mode="messages",
            ):
                if not isinstance(chunk, AIMessageChunk):
                    continue

                text = _message_to_text(chunk)
                if text:
                    yield text

    async def close(self) -> None:
        self._thread_locks.clear()
        await close_agent_checkpointer()


async def create_agent_runtime(rag_runtime: RagRuntime) -> AgentRuntime:
    checkpointer = await init_agent_checkpointer()
    return AgentRuntime(checkpointer=checkpointer, rag_runtime=rag_runtime)


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise RuntimeError("Agent runtime is not initialized.")
    return runtime
