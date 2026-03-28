from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from pydantic import BaseModel, Field
from typing import Literal

from dotenv import load_dotenv
from fastapi import Request
from langchain_core.messages import (AIMessage, AIMessageChunk, AnyMessage, HumanMessage, SystemMessage)
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from app.dependencies.db import close_agent_checkpointer, init_agent_checkpointer
from app.core.state import TeachingAssistantState, TeachingMetadata

load_dotenv()

INTERRUPT_FOR_USERINPUT_NODE = "interrupt_for_userinput"
MAX_METADATA_HUMAN_MESSAGES = 3

def get_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        streaming=streaming,
    )

llm = get_model(streaming=True)
structured_output_llm = get_model(streaming=False)

class IntentRoute(BaseModel):
    intent: Literal["normal_chat", "teaching_plan"] = Field(None, description="User's intention")

router = structured_output_llm.with_structured_output(
    IntentRoute,
    method="json_schema",
    strict=True
)
metadata_extractor = structured_output_llm.with_structured_output(
    TeachingMetadata,
    method="json_schema",
    strict=True,
)


# 意图识别路由节点
def intent_router_node(state: TeachingAssistantState):
    decision = router.invoke(
        [
            SystemMessage(
                content="你是意图分析和路由节点，你需要分析用户输入的内容的意图，并格式化输出JSON，如果是日常对话,intent字段为：'normal_chat'。如果让你帮助备课，生成教案课件等，intent字段为：'teaching_plan'"
            ),
            state["messages"][-1],
        ]
    )
    print(f"【意图识别路由节点】路由结果：{decision.intent}")
    return {"intent": decision.intent}


def route_decision(state: TeachingAssistantState):
    if state["intent"] == "normal_chat":
        return "normal_chat_node"
    elif state["intent"] == "teaching_plan":
        return "metadata_structer_node"
    else:
        return "Error"

# 普通日常聊天节点
def normal_chat_node(state: TeachingAssistantState):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

# 结构化元数据节点
def metadata_structer_node(state: TeachingAssistantState):
    system_prompt = f"你是一个帮助老师备课的智能体中的结构化元数据节点，你的任务是根据已有JSON或上下文把用户提到的教学要素提取出来并结构化输出为JSON格式,用户没有提到的要素为None。当所有要素都有时is_complete为true，否则为false。目前已经有的教学要素JSON是：{state["teaching_metadata"]}"
    original_messages = state["messages"]
    start_time = time.perf_counter()
    print(
        "【结构化元数据节点】开始抽取，"
        f"original_messages={len(original_messages)}，"
    )
    response = metadata_extractor.invoke([SystemMessage(content=system_prompt)] + [ msg for msg in original_messages if isinstance(msg, HumanMessage)])
    duration_ms = (time.perf_counter() - start_time) * 1000
    print(f"【结构化元数据节点】结构化调用耗时：{duration_ms:.2f}ms")
    print(f"【结构化元数据节点】结构化元数据结果：{str(response)}")
    return {"teaching_metadata": response}

# 元数据完整性验证条件边
def metadata_completion_condition(state: TeachingAssistantState):
    if state["teaching_metadata"]["is_complete"]:
        print("【元数据完整性验证】验证结果为 is complete")
        return "teaching_design_planner"
    else:
        print("【元数据完整性验证】验证结果为 not complete")
        return "follow_up_questioner"

# 主动追问节点，下一节点为结构化元数据节点
def follow_up_questioner(state: TeachingAssistantState):
    system_prompt = f"你是一个帮助老师备课的智能体中的主动追问节点，你需要联系上下文和提供的教学要素，主动追问用户补充教学要素，目前的教学要素是：{state["teaching_metadata"]},其中为None的是缺失的。"
    # 不携带历史消息上下文
    response = llm.invoke([SystemMessage(content=system_prompt)])
    print("【主动追问节点】进行一次主动追问")
    return {"messages": [response]}

# 中断等待用户输入节点
def interrupt_for_userinput(state: TeachingAssistantState):
    print("【中断节点】正在中断，等待用户输入")
    user_input = interrupt({"question": state["messages"][-1].content})
    print("【中断节点】中断恢复")
    return {"messages": user_input}

# RAG检索节点
def rag_retrieval_node(state: TeachingAssistantState):
    pass

# 教学设计总体计划节点
def teaching_design_planner(state: TeachingAssistantState):
    system_prompt = f"你是一个帮助老师备课生成教学计划的智能体，根据用户提供的信息、教学元数据以及检索到的相关资料，进行教学计划的总体设计。教学元数据：{state["teaching_metadata"]}。"
    response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    print("【总体计划节点】正在输出总体计划")
    return {"teaching_design_plan": [response], "messages": [response]}


def build_agent_graph(*, streaming: bool = False, checkpointer: AsyncPostgresSaver):
    agent_builder = StateGraph(TeachingAssistantState)
    agent_builder.add_node("intent_router_node", intent_router_node)
    agent_builder.add_node("normal_chat_node", normal_chat_node)
    agent_builder.add_node("metadata_structer_node", metadata_structer_node)
    agent_builder.add_node("follow_up_questioner", follow_up_questioner)
    agent_builder.add_node("interrupt_for_userinput", interrupt_for_userinput)
    agent_builder.add_node("teaching_design_planner", teaching_design_planner)


    agent_builder.add_edge(START, "intent_router_node")
    agent_builder.add_conditional_edges(
        "intent_router_node",
        route_decision,
        {
            "normal_chat_node": "normal_chat_node",
            "metadata_structer_node": "metadata_structer_node"
        },
    )
    agent_builder.add_edge("normal_chat_node", END)
    agent_builder.add_conditional_edges(
        "metadata_structer_node",
        metadata_completion_condition,
        {
            "teaching_design_planner": "teaching_design_planner",
            "follow_up_questioner": "follow_up_questioner"
        }
    )
    agent_builder.add_edge("follow_up_questioner", "interrupt_for_userinput")
    agent_builder.add_edge("interrupt_for_userinput", "metadata_structer_node")

    return agent_builder.compile(checkpointer=checkpointer)


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

    async def _should_resume_thread(self, thread_id: str) -> bool:
        state_snapshot = await self.graph.aget_state(get_thread_config(thread_id))
        interrupts = getattr(state_snapshot, "interrupts", ()) or ()
        next_nodes = tuple(getattr(state_snapshot, "next", ()) or ())
        return bool(interrupts) and INTERRUPT_FOR_USERINPUT_NODE in next_nodes

    async def _get_graph_input(self, message: str, thread_id: str):
        if await self._should_resume_thread(thread_id):
            return Command(resume=message)
        return {"messages": [HumanMessage(content=message)]}

    async def invoke_agent(self, message: str, thread_id: str) -> str:
        lock = await self._get_thread_lock(thread_id)
        async with lock:
            graph_input = await self._get_graph_input(message, thread_id)
            result = await self.graph.ainvoke(
                graph_input,
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
            graph_input = await self._get_graph_input(message, thread_id)
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


async def create_agent_runtime() -> AgentRuntime:
    checkpointer = await init_agent_checkpointer()
    return AgentRuntime(checkpointer=checkpointer)


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise RuntimeError("Agent runtime is not initialized.")
    return runtime
