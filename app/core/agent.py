from __future__ import annotations

import operator
import os
import threading
from collections.abc import Iterator
from typing import Annotated, Literal, TypedDict
from urllib.parse import quote, urlparse

from dotenv import load_dotenv
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
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg import Connection
from psycopg.rows import dict_row

load_dotenv()

SYSTEM_PROMPT = (
    "You are a helpful assistant. Continue the conversation based on the stored "
    "session context and use available tools when arithmetic is needed."
)
CHECKPOINT_NAMESPACE = "chat"

_agent_graph = None
_streaming_agent_graph = None
_checkpointer: PostgresSaver | None = None
_checkpoint_connection: Connection | None = None
_init_lock = threading.Lock()


def get_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        streaming=streaming,
    )


def get_postgres_conn_string() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if database_url:
        return database_url

    raw_host = os.getenv("DB_HOST", "localhost")
    parsed = urlparse(raw_host if "://" in raw_host else f"//{raw_host}")
    host = parsed.hostname or raw_host.split(":")[0]
    port = parsed.port or int(os.getenv("DB_PORT", "5432"))
    database = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB") or "postgres"
    user = quote(os.getenv("DB_USER", "postgres"))
    password = quote(os.getenv("DB_PASSWORD", ""))
    sslmode = os.getenv("DB_SSLMODE")

    conn_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    if sslmode:
        conn_string = f"{conn_string}?sslmode={sslmode}"
    return conn_string


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

    def llm_call_node(state: MessageState) -> MessageState:
        response = model_with_tools.invoke(
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

        results.append(
            ToolMessage(content=content, tool_call_id=tool_call["id"])
        )

    return {"messages": results}


def should_continue(state: MessageState) -> Literal["tool_call", END]:
    tool_calls = getattr(state["messages"][-1], "tool_calls", []) or []
    if tool_calls:
        return "tool_call"
    return END


def build_agent_graph(*, streaming: bool = False, checkpointer: PostgresSaver):
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


def _ensure_graphs():
    global _agent_graph
    global _streaming_agent_graph
    global _checkpointer
    global _checkpoint_connection

    if _agent_graph is not None and _streaming_agent_graph is not None:
        return

    with _init_lock:
        if _agent_graph is not None and _streaming_agent_graph is not None:
            return

        if _checkpointer is None:
            _checkpoint_connection = Connection.connect(
                get_postgres_conn_string(),
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
            )
            _checkpointer = PostgresSaver(conn=_checkpoint_connection)
            _checkpointer.setup()

        _agent_graph = build_agent_graph(checkpointer=_checkpointer)
        _streaming_agent_graph = build_agent_graph(
            streaming=True,
            checkpointer=_checkpointer,
        )


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


def invoke_agent(message: str, thread_id: str) -> str:
    _ensure_graphs()
    result = _agent_graph.invoke(
        {"messages": [HumanMessage(content=message)]},
        config=get_thread_config(thread_id),
    )
    return get_final_response_text(result["messages"])


def stream_agent_response(message: str, thread_id: str) -> Iterator[str]:
    _ensure_graphs()
    for chunk, metadata in _streaming_agent_graph.stream(
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


async def close_agent_resources() -> None:
    global _agent_graph
    global _streaming_agent_graph
    global _checkpointer
    global _checkpoint_connection

    if _checkpoint_connection is not None:
        _checkpoint_connection.close()

    _agent_graph = None
    _streaming_agent_graph = None
    _checkpointer = None
    _checkpoint_connection = None
