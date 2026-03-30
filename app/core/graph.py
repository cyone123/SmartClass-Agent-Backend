from __future__ import annotations

import json
import time
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.core.llm import llm, structured_output_llm
from app.core.rag import RagRuntime
from app.core.state import TeachingAssistantState, TeachingMetadata


class IntentRoute(BaseModel):
    intent: Literal["normal_chat", "teaching_plan"] = Field(
        None,
        description="User's intention",
    )


router = structured_output_llm.with_structured_output(
    IntentRoute,
    method="json_schema",
    strict=True,
)
metadata_extractor = structured_output_llm.with_structured_output(
    TeachingMetadata,
    method="json_schema",
    strict=True,
)


def intent_router_node(state: TeachingAssistantState):
    decision = router.invoke(
        [
            SystemMessage(
                content=(
                    "你是意图分析和路由节点。"
                    "请判断用户输入是普通聊天还是备课/教学设计相关请求，"
                    "并按 JSON 输出 intent。"
                    "普通聊天输出 normal_chat，备课类输出 teaching_plan。"
                )
            ),
            state["messages"][-1],
        ]
    )
    print(f"【意图识别路由节点】路由结果：{decision.intent}")
    return {"intent": decision.intent}


def route_decision(state: TeachingAssistantState):
    if state["intent"] == "normal_chat":
        return "normal_chat_node"
    if state["intent"] == "teaching_plan":
        return "metadata_structer_node"
    return "Error"


def normal_chat_node(state: TeachingAssistantState):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


def metadata_structer_node(state: TeachingAssistantState):
    current_metadata = state.get("teaching_metadata")
    system_prompt = (
        "你是一个帮助老师备课的智能体中的结构化元数据节点。"
        "请根据已有 JSON 和用户上下文，提取教学要素并输出 JSON。"
        "用户没有提到的字段填 None。"
        "当关键信息已完整可用于检索与教学设计时，is_complete 设为 true，否则为 false。"
        f"当前已提取教学要素：{current_metadata}"
    )
    original_messages = state["messages"]
    start_time = time.perf_counter()
    print(
        "【结构化元数据节点】开始抽取，"
        f"original_messages={len(original_messages)}，"
    )
    response = metadata_extractor.invoke(
        [SystemMessage(content=system_prompt)]
        + [msg for msg in original_messages if isinstance(msg, HumanMessage)]
    )
    duration_ms = (time.perf_counter() - start_time) * 1000
    print(f"【结构化元数据节点】结构化调用耗时：{duration_ms:.2f}ms")
    print(f"【结构化元数据节点】结构化元数据结果：{response}")
    return {"teaching_metadata": response}


def metadata_completion_condition(state: TeachingAssistantState):
    metadata = state.get("teaching_metadata")
    if metadata and metadata.get("is_complete"):
        print("【元数据完整性验证】验证结果：is_complete")
        return "rag_retrieval_node"

    print("【元数据完整性验证】验证结果：not_complete")
    return "follow_up_questioner"


def follow_up_questioner(state: TeachingAssistantState):
    system_prompt = (
        "你是一个帮助老师备课的智能体中的主动追问节点。"
        "请根据当前缺失的教学要素，向用户提出一个最关键、最简洁的问题。"
        f"当前教学要素：{state.get('teaching_metadata')}"
    )
    response = llm.invoke([SystemMessage(content=system_prompt)])
    print("【主动追问节点】发起一次主动追问")
    return {"messages": [response]}


def interrupt_for_userinput(state: TeachingAssistantState):
    print("【中断节点】正在中断，等待用户输入")
    user_input = interrupt({"question": state["messages"][-1].content})
    print("【中断节点】中断恢复")
    return {"messages": [HumanMessage(content=user_input)]}


def _message_to_text(message: AIMessage | HumanMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)
    return str(content)


def _build_rag_query(state: TeachingAssistantState) -> str:
    metadata = state.get("teaching_metadata") or {}
    query_messages = [
        _message_to_text(msg).strip()
        for msg in state.get("messages", [])[-2:-1]
        if isinstance(msg, (HumanMessage, AIMessage))
    ]
    query_parts = [
        f"教学元数据: {json.dumps(metadata, ensure_ascii=False)}",
        f"用户问题: {' '.join(message for message in query_messages if message)}",
    ]
    return "\n".join(part for part in query_parts if part.strip())


def teaching_design_planner(state: TeachingAssistantState):
    system_prompt = (
        "你是一个帮助老师备课生成教学计划的多智能体中的总体生成规划节点。"
        "请根据用户提供的信息要求、教学元数据和检索到的参考资料，"
        "输出一份完整且可执行的教学设计计划，以供后续生成PPT和教案的节点参考。"
        f"教学元数据：{state.get('teaching_metadata')}\n"
        f"RAG 上下文：{state.get('rag_context', '')}"
    )
    response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    print("【总体计划节点】正在输出总体计划")
    return {
        "teaching_design_plan": _message_to_text(response).strip(),
        "messages": [response],
    }


def build_agent_graph(
    *,
    streaming: bool = False,
    checkpointer: AsyncPostgresSaver,
    rag_runtime: RagRuntime,
):
    async def rag_retrieval_node(state: TeachingAssistantState):
        query = _build_rag_query(state)
        result = await rag_runtime.retrieval(query)
        print(f"【RAG 检索节点】原始检索结果数量：{len(result)}")
        print(f"【RAG 检索节点】原始检索结果：{str(result)}")
        rag_context = "\n\n".join(document.page_content for document in result)
        return {"rag_context": rag_context}

    agent_builder = StateGraph(TeachingAssistantState)
    agent_builder.add_node("intent_router_node", intent_router_node)
    agent_builder.add_node("normal_chat_node", normal_chat_node)
    agent_builder.add_node("metadata_structer_node", metadata_structer_node)
    agent_builder.add_node("follow_up_questioner", follow_up_questioner)
    agent_builder.add_node("interrupt_for_userinput", interrupt_for_userinput)
    agent_builder.add_node("rag_retrieval_node", rag_retrieval_node)
    agent_builder.add_node("teaching_design_planner", teaching_design_planner)

    agent_builder.add_edge(START, "intent_router_node")
    agent_builder.add_conditional_edges(
        "intent_router_node",
        route_decision,
        {
            "normal_chat_node": "normal_chat_node",
            "metadata_structer_node": "metadata_structer_node",
        },
    )
    agent_builder.add_edge("normal_chat_node", END)
    agent_builder.add_conditional_edges(
        "metadata_structer_node",
        metadata_completion_condition,
        {
            "rag_retrieval_node": "rag_retrieval_node",
            "follow_up_questioner": "follow_up_questioner",
        },
    )
    agent_builder.add_edge("follow_up_questioner", "interrupt_for_userinput")
    agent_builder.add_edge("interrupt_for_userinput", "metadata_structer_node")
    agent_builder.add_edge("rag_retrieval_node", "teaching_design_planner")
    agent_builder.add_edge("teaching_design_planner", END)

    return agent_builder.compile(checkpointer=checkpointer)
