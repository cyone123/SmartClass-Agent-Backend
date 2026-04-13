from __future__ import annotations

import json
import time
from typing import Literal, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.core.llm import llm, structured_output_llm
from app.core.progress import emit_progress
from app.core.rag import RagRuntime
from app.core.state import TeachingAssistantState, TeachingMetadata

ATTACHMENT_MESSAGE_PREFIX = "用户上传的附件内容（仅供本轮对话参考）：\n"


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
    strict=True
)


def build_input_messages(
    message: str,
    attachment_text: str | None = None,
    attachment_paths: list[str] | None = None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if attachment_text:
        messages.append(
            SystemMessage(
                content=(
                    f"{ATTACHMENT_MESSAGE_PREFIX}{attachment_text}\n"
                    f"附件存储路径：{attachment_paths}"
                )
            )
        )
    messages.append(HumanMessage(content=message))
    return messages


def intent_router_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "intent_recognition", "running")

    try:
        decision = router.invoke(
            [
                SystemMessage(
                    content=(
                        "You are an intent analysis and routing node in an multi-agent workflow whose target user is teachers. "
                        "The workflow have two ways.One way is to help teacher prepare lessons or generate teaching plan. "
                        "Another way is normal chat in which user can talk about any things irrelevant with teaching. "
                        "Please determine the user's intent based on the provided conversations, and strictly "
                        "output a JSON string without any extra content. "
                        "For lesson preparation/teaching design related requests, output "
                        "'teaching_plan'. For other requests, output 'normal_chat'. "
                        'For example, your output must be: {"intent": "normal_chat"} or '
                        '{"intent": "teaching_plan"}.'
                    )
                ),
            ] + state["messages"][-4:]
        )
        print(f"[intent_router_node] intent:{decision.intent}")
        if reporter:
            reporter.emit(
                "intent_recognition",
                "success",
                detail=(
                    "已识别为教学设计请求"
                    if decision.intent == "teaching_plan"
                    else "已识别为普通对话"
                ),
            )
        return {"intent": decision.intent}
    except Exception as exc:
        if reporter:
            reporter.emit("intent_recognition", "failed", detail=str(exc))
        raise


def route_decision(state: TeachingAssistantState):
    if state["intent"] == "normal_chat":
        return "normal_chat_node"
    if state["intent"] == "teaching_plan":
        return "metadata_structer_node"
    return "Error"


async def normal_chat_node(state: TeachingAssistantState):
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}


def metadata_structer_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "metadata_structuring", "running")

    current_metadata = state.get("teaching_metadata")
    system_prompt = (
        "You are a structured metadata node in an intelligent agent that helps teachers "
        "prepare lessons. Please extract teaching elements based on the user's messages "
        "and output JSON strictly according to given fomart. Ensure all information is obtained from the user "
        "and do not fabricate missing details. Fill incomplete fields with None. Set "
        "is_complete to true when the elements are complete enough for retrieval and "
        "instructional design. "
        f"Currently extracted teaching elements: {current_metadata}"
    )
    original_messages = state["messages"]
    start_time = time.perf_counter()
    print(
        "[metadata_structer_node] start "
        f"original_messages={len(original_messages)}"
    )

    try:
        response = metadata_extractor.invoke(
            [SystemMessage(content=system_prompt)]
            + [msg for msg in original_messages if isinstance(msg, HumanMessage)]
        )
        duration_ms = (time.perf_counter() - start_time) * 1000
        print(f"[metadata_structer_node] duration_ms={duration_ms:.2f}")
        print(f"[metadata_structer_node] response={response}")
        if reporter:
            reporter.emit(
                "metadata_structuring",
                "success",
                detail=(
                    "已提取结构化元数据"
                    if response.get("is_complete")
                    else "已提取结构化信息，仍需补充字段"
                ),
            )
        return {"teaching_metadata": response}
    except Exception as exc:
        if reporter:
            reporter.emit("metadata_structuring", "failed", detail=str(exc))
        raise


def metadata_completion_condition(state: TeachingAssistantState):
    metadata = state.get("teaching_metadata")
    if metadata and metadata.get("is_complete"):
        print("[metadata_completion_condition] is_complete=true")
        return "rag_retrieval_node"

    print("[metadata_completion_condition] is_complete=false")
    return "follow_up_questioner"


async def follow_up_questioner(state: TeachingAssistantState):
    system_prompt = (
        "你是一个帮助老师备课的智能体中的主动追问节点。"
        "请根据当前缺失的教学要素，向用户提出问题来补全要素。"
        # f"用户的上一个回答：{state["messages"][-1].content}"
        f"当前教学要素：{state.get('teaching_metadata')}"
    )
    response = await llm.ainvoke([SystemMessage(content=system_prompt)])
    print("[follow_up_questioner] ask follow-up question")
    return {"messages": [response]}


def interrupt_for_userinput(state: TeachingAssistantState):
    print("[interrupt_for_userinput] waiting for user input")
    user_input = interrupt({"question": state["messages"][-1].content})
    print("[interrupt_for_userinput] resumed")
    if isinstance(user_input, dict):
        return {
            "messages": build_input_messages(
                user_input.get("message", ""),
                user_input.get("attachment_text"),
                user_input.get("attachment_paths"),
            )
        }
    return {"messages": build_input_messages(str(user_input))}


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
    human_messages = [
        _message_to_text(msg).strip()
        for msg in state.get("messages", [])
        if isinstance(msg, HumanMessage)
    ]
    query_parts = [
        f"教学元数据: {json.dumps(metadata, ensure_ascii=False)}",
        f"用户问题: {' '.join(message for message in human_messages if message)}",
    ]
    return "\n".join(part for part in query_parts if part.strip())


async def teaching_design_planner(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "teaching_design", "running")

    system_prompt = (
        "你是一个帮助老师备课生成教学设计的总体规划节点。"
        "请根据用户需求、教学元数据和检索到的参考资料，输出一份完整且可执行的教学设计计划，"
        "供后续生成 PPT 和教案节点参考。"
        f"教学元数据：{state.get('teaching_metadata')}\n"
        f"RAG 上下文：{state.get('rag_context', '')}"
    )

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt)] + state["messages"],
        )
        print("===[teaching_design_planner] generated teaching design plan===")
        if reporter:
            reporter.emit("teaching_design", "success", detail="已生成教学设计")
        return {
            "teaching_design_plan": _message_to_text(response).strip(),
            "messages": [response],
        }
    except Exception as exc:
        if reporter:
            reporter.emit("teaching_design", "failed", detail=str(exc))
        raise


def build_agent_graph(
    *,
    streaming: bool = False,
    checkpointer: AsyncPostgresSaver,
    rag_runtime: RagRuntime,
    agent_runnable,
):
    async def rag_retrieval_node(
        state: TeachingAssistantState,
        config: Optional[RunnableConfig] = None,
    ):
        reporter = emit_progress(config, "rag_retrieval", "running")

        try:
            query = _build_rag_query(state)
            result = await rag_runtime.retrieval(
                query,
                plan_id=state.get("plan_id"),
            )
            print(f"[rag_retrieval_node] raw_result_count={len(result)}")
            rag_results = [
                {
                    "page_content": document.page_content,
                    "metadata": document.metadata,
                }
                for document in result
            ]
            rag_context = "\n\n".join(document["page_content"] for document in rag_results)
            if reporter:
                reporter.emit(
                    "rag_retrieval",
                    "success",
                    detail=f"已检索到 {len(rag_results)} 条相关内容",
                )
            return {"rag_results": rag_results, "rag_context": rag_context}
        except Exception as exc:
            if reporter:
                reporter.emit("rag_retrieval", "failed", detail=str(exc))
            raise

    agent_builder = StateGraph(TeachingAssistantState)
    agent_builder.add_node("intent_router_node", intent_router_node)
    agent_builder.add_node("normal_chat_node", normal_chat_node)
    agent_builder.add_node("metadata_structer_node", metadata_structer_node)
    agent_builder.add_node("follow_up_questioner", follow_up_questioner)
    agent_builder.add_node("interrupt_for_userinput", interrupt_for_userinput)
    agent_builder.add_node("rag_retrieval_node", rag_retrieval_node)
    agent_builder.add_node("teaching_design_planner", teaching_design_planner)
    agent_builder.add_node("ppt_generate_node", agent_runnable)

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
    # agent_builder.add_edge("teaching_design_planner", END)
    agent_builder.add_edge("teaching_design_planner", "ppt_generate_node")
    agent_builder.add_edge("ppt_generate_node", END)

    return agent_builder.compile(checkpointer=checkpointer)
