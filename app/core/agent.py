from __future__ import annotations

import asyncio
import operator
import os
from collections.abc import AsyncIterator
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from fastapi import Request
from langchain.tools import tool
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from app.dependencies.db import close_agent_checkpointer, init_agent_checkpointer

load_dotenv()

SYSTEM_PROMPT = (
    "You are a helpful assistant. Continue the conversation based on the stored "
    "session context and use available tools when needed."
)
CHECKPOINT_NAMESPACE = "chat"


def get_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        streaming=streaming,
    )


@tool(description="Add two numbers together")
def add(a: int, b: int) -> int:
    return a + b


@tool(description="Divide two numbers")
def divide(a: int, b: int) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


@tool(description="Multiply two numbers")
def multiply(a: int, b: int) -> int:
    return a * b


TOOLS = [add, divide, multiply]
TOOLS_DICT = {tool_item.name: tool_item for tool_item in TOOLS}


class MessageState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]


def _build_model_with_tools(*, streaming: bool = False):
    return get_model(streaming=streaming).bind_tools(TOOLS)


def llm_call_node_factory(*, streaming: bool = False):
    model_with_tools = _build_model_with_tools(streaming=streaming)

    async def llm_call_node(state: MessageState) -> MessageState:
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}

    return llm_call_node


def tool_call_node(state: MessageState) -> dict[str, list[ToolMessage]]:
    results: list[ToolMessage] = []
    tool_calls = getattr(state["messages"][-1], "tool_calls", []) or []

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        selected_tool = TOOLS_DICT.get(tool_name)

        if selected_tool is None:
            content = f"Tool '{tool_name}' is not registered."
        else:
            try:
                tool_result = selected_tool.invoke(tool_call["args"])
                content = str(tool_result)
            except Exception as exc:
                content = f"Tool '{tool_name}' failed: {exc}"

        results.append(ToolMessage(content=content, tool_call_id=tool_call["id"]))

    return {"messages": results}


def should_continue(state: MessageState) -> Literal["tool_call", END]:
    tool_calls = getattr(state["messages"][-1], "tool_calls", []) or []
    if tool_calls:
        return "tool_call"
    return END


def build_agent_graph(*, streaming: bool = False, checkpointer: AsyncPostgresSaver):
    agent_builder = StateGraph(MessageState)
    agent_builder.add_node("llm_call", llm_call_node_factory(streaming=streaming))
    agent_builder.add_node("tool_call", tool_call_node)

    agent_builder.add_edge(START, "llm_call")
    agent_builder.add_conditional_edges(
        "llm_call",
        should_continue,
        {
            "tool_call": "tool_call",
            END: END,
        },
    )
    agent_builder.add_edge("tool_call", "llm_call")

    return agent_builder.compile(checkpointer=checkpointer)


def get_thread_config(thread_id: str) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": CHECKPOINT_NAMESPACE,
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
    def __init__(self, checkpointer: AsyncPostgresSaver) -> None:
        self.checkpointer = checkpointer
        self.graph = build_agent_graph(checkpointer=checkpointer)
        self.streaming_graph = build_agent_graph(
            streaming=True,
            checkpointer=checkpointer,
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

    async def invoke_agent(self, message: str, thread_id: str) -> str:
        lock = await self._get_thread_lock(thread_id)
        async with lock:
            result = await self.graph.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config=get_thread_config(thread_id),
            )
        return get_final_response_text(result["messages"])

    async def stream_agent_response(
        self,
        message: str,
        thread_id: str,
    ) -> AsyncIterator[str]:
        lock = await self._get_thread_lock(thread_id)
        async with lock:
            async for chunk, metadata in self.streaming_graph.astream(
                {"messages": [HumanMessage(content=message)]},
                config=get_thread_config(thread_id),
                stream_mode="messages",
            ):
                if metadata.get("langgraph_node") != "llm_call":
                    continue
                if not isinstance(chunk, AIMessageChunk):
                    continue

                text = _message_to_text(chunk)
                if text:
                    yield text

    async def close(self) -> None:
        self._thread_locks.clear()
        await close_agent_checkpointer()


async def create_agent_runtime() -> AgentRuntime:
    checkpointer = await init_agent_checkpointer()
    return AgentRuntime(checkpointer=checkpointer)


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise RuntimeError("Agent runtime is not initialized.")
    return runtime
