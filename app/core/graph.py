from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, Mapping, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from app.core.llm import llm, structured_output_llm
from app.core.progress import emit_progress
from app.core.rag import RagRuntime
from app.core.state import TeachingAssistantState, TeachingMetadata

ATTACHMENT_MESSAGE_PREFIX = "用户上传的附件内容，供当前轮对话参考：\n"


INTERRUPT_FOR_USERINPUT_NODE = "interrupt_for_userinput"
METADATA_REVIEW_INTERRUPT_NODE = "metadata_review_interrupt_node"
TEACHING_PLAN_REVIEW_INTERRUPT_NODE = "teaching_plan_review_interrupt_node"
APPROVAL_INTERRUPT_NODES = {
    METADATA_REVIEW_INTERRUPT_NODE,
    TEACHING_PLAN_REVIEW_INTERRUPT_NODE,
}
RESUMABLE_INTERRUPT_NODES = {
    INTERRUPT_FOR_USERINPUT_NODE,
    *APPROVAL_INTERRUPT_NODES,
}
APPROVAL_STAGE_BY_NODE = {
    METADATA_REVIEW_INTERRUPT_NODE: "metadata_review",
    TEACHING_PLAN_REVIEW_INTERRUPT_NODE: "teaching_plan_review",
}


class IntentRoute(BaseModel):
    intent: Literal["normal_chat", "teaching_plan"] = Field(
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


def _build_resume_message_update(user_input: Any) -> dict[str, list[BaseMessage]]:
    if isinstance(user_input, Mapping):
        return {
            "messages": build_input_messages(
                str(user_input.get("message", "") or ""),
                user_input.get("attachment_text"),
                user_input.get("attachment_paths"),
            )
        }
    return {"messages": build_input_messages(str(user_input))}


def metadata_review_interrupt_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    # reporter = emit_progress(config, "metadata_review", "running", detail="等待教师确认教学要素")
    user_input = interrupt(
        _build_approval_payload(
            "metadata_review",
            metadata=state.get("teaching_metadata") or {},
        )
    )
    if _is_approve_action(user_input):
        # if reporter:
        #     reporter.emit("metadata_review", "success", detail="已确认教学要素")
        return Command(goto="rag_retrieval_node")
    return Command(
        update=_build_resume_message_update(user_input),
        goto="metadata_structer_node",
    )


def _is_approve_action(user_input: Any) -> bool:
    return isinstance(user_input, Mapping) and user_input.get("action") == "approve"


def _build_approval_payload(
    stage: Literal["metadata_review", "teaching_plan_review"],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "title": "确认结构化教学要素" if stage == "metadata_review" else "确认教学计划",
        "description": (
            "已提取当前教学要素，请确认后继续生成教学计划。"
            if stage == "metadata_review"
            else "教学计划已生成，请确认是否继续生成课件、教案和互动内容。"
        ),
        "confirm_label": "确认并继续",
        "cancel_label": "取消并修改",
    }
    if stage == "metadata_review":
        payload["metadata"] = dict(metadata or {})
    return payload


def get_pending_approval_payload(
    interrupts: Sequence[Any] | None,
    next_nodes: Sequence[str] | None,
) -> dict[str, Any] | None:
    pending_nodes = tuple(next_nodes or ())
    pending_interrupts = tuple(interrupts or ())
    for node_name in pending_nodes:
        if node_name not in APPROVAL_INTERRUPT_NODES:
            continue
        for pending_interrupt in pending_interrupts:
            payload = getattr(pending_interrupt, "value", None)
            if not isinstance(payload, Mapping):
                continue
            approval_payload = dict(payload)
            approval_payload["interrupt_id"] = getattr(pending_interrupt, "id", "")
            approval_payload.setdefault("stage", APPROVAL_STAGE_BY_NODE[node_name])
            return approval_payload
    return None


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


def intent_router_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "intent_recognition", "running")
    try:
        print(f"[意图识别节点] 开始识别")
        decision = router.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a intention recogonition and router node in a teacher-facing multi-agent workflow. "
                        "Determine which way to go based on user' message. "
                        "Return `teaching_plan` for lesson preparation, teaching design, "
                        "courseware, lesson-plan, or interactive activity requests. "
                        "Return `normal_chat` for everything else."
                        "Output in JSON format strictly and no any other character."
                        'For exmaple: {"intent": "normal_chat"} or {"intent": "teaching_plan"}. '
                        'Do not output like this: "json\n{"intent": "normal_chat"}\n"'
                    )
                ),
            ] + [ msg for msg in state["messages"] if isinstance(msg, (HumanMessage, AIMessage))][-4:]
        )
        print(f"[意图识别节点] intent:{decision.intent}")
        if reporter:
            reporter.emit(
                "intent_recognition",
                "success",
                detail=(
                    "识别为教学设计请求"
                    if decision.intent == "teaching_plan"
                    else "识别为普通对话"
                ),
            )
        return {"intent": decision.intent}
    except Exception as exc:
        if reporter:
            reporter.emit("intent_recognition", "failed", detail=str(exc))
        raise


def route_decision(state: TeachingAssistantState):
    if state.get("intent") == "normal_chat":
        return "normal_chat_node"
    if state.get("intent") == "teaching_plan":
        return "metadata_structer_node"
    return "error"


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
        "You extract structured teaching metadata for a teacher assistant. "
        "Use only the user's provided information. Fill missing fields with None. "
        "Set `is_complete` to true only when the metadata is complete enough for "
        "retrieval and instructional design. "
        "Do not explicitly contain 'json'. Do not contain newline character.\n"
        f"Current metadata: {current_metadata}"
    )
    start_time = time.perf_counter()

    try:
        print("[结构化元数据节点] start ")
        response = metadata_extractor.invoke(
            [SystemMessage(content=system_prompt)]
            + [msg for msg in state["messages"] if isinstance(msg, HumanMessage)]
        )
        duration_ms = (time.perf_counter() - start_time) * 1000
        print(f"[结构化元数据节点] 元数据：{response}")
        print(f"[结构化元数据节点] 持续时间_ms={duration_ms:.2f}")
        if reporter:
            reporter.emit(
                "metadata_structuring",
                "success",
                detail=(
                    "已提取结构化教学要素"
                    if response.get("is_complete")
                    else "已提取结构化信息，仍需补充需求"
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
        print("[元数据完整性验证] is_complete=true")
        return METADATA_REVIEW_INTERRUPT_NODE

    print("[元数据完整性验证] is_complete=false")
    return "follow_up_questioner"


async def follow_up_questioner(state: TeachingAssistantState):
    system_prompt = (
        "你是教学助手中的追问节点，需要主动追问用户来补充教学要素。"
        "请根据当前缺失的教学要素，向用户提出关键、自然、合适的补充问题。\n"
        f"当前教学要素：{state.get('teaching_metadata')}"
    )
    response = await llm.ainvoke([SystemMessage(content=system_prompt)])
    print("[主动追问节点] ask follow-up question")
    return {"messages": [response]}


def interrupt_for_userinput(state: TeachingAssistantState):
    print("[中断等待用户输入] waiting for user input")
    user_input = interrupt({"question": state["messages"][-1].content})
    print("[中断恢复] resumed")
    if isinstance(user_input, dict):
        return {
            "messages": build_input_messages(
                user_input.get("message", ""),
                user_input.get("attachment_text"),
                user_input.get("attachment_paths"),
            )
        }
    return {"messages": build_input_messages(str(user_input))}


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
        "你是一个教师助理中的教学设计规划节点。"
        "请根据用户需求、结构化教学要素和检索上下文，输出一份完整、可执行的教学设计方案。"
        "这份结果将作为后续课件、教案和互动内容生成的直接输入。\n"
        f"教学元数据：{state.get('teaching_metadata')}\n"
        f"RAG 上下文：{state.get('rag_context', '')}"
    )

    try:
        response = await llm.ainvoke([SystemMessage(content=system_prompt)] + state["messages"])
        if reporter:
            reporter.emit("teaching_design", "success", detail="已生成教学设计方案")
        return {
            "teaching_design_plan": _message_to_text(response).strip(),
            "messages": [response],
        }
    except Exception as exc:
        if reporter:
            reporter.emit("teaching_design", "failed", detail=str(exc))
        raise


def teaching_plan_review_interrupt_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "teaching_plan_review", "running", detail="等待教师确认教学计划")
    user_input = interrupt(_build_approval_payload("teaching_plan_review"))
    if _is_approve_action(user_input):
        if reporter:
            reporter.emit("teaching_plan_review", "success", detail="已确认教学计划")
        return Command(goto=["ppt_generate_node", "docx_generate_node", "html_game_generate_node"])
    return Command(
        update=_build_resume_message_update(user_input),
        goto="teaching_design_planner",
    )


def build_agent_graph(
    *,
    checkpointer: AsyncPostgresSaver,
    rag_runtime: RagRuntime,
    ppt_generate_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    docx_generate_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    html_generate_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
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
            rag_results = [
                {
                    "page_content": document.page_content,
                    "metadata": document.metadata,
                }
                for document in result
            ]
            rag_context = "\n\n".join(document["page_content"] for document in rag_results)
            print(f"[RAG节点] 检索到资料={rag_context}")
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

    async def artifact_fan_in_node(state: TeachingAssistantState, config: RunnableConfig | None = None):
        _ = state
        _ = config
        return {}

    agent_builder = StateGraph(TeachingAssistantState)
    agent_builder.add_node("intent_router_node", intent_router_node)
    agent_builder.add_node("normal_chat_node", normal_chat_node)
    agent_builder.add_node("metadata_structer_node", metadata_structer_node)
    agent_builder.add_node("follow_up_questioner", follow_up_questioner)
    agent_builder.add_node(INTERRUPT_FOR_USERINPUT_NODE, interrupt_for_userinput)
    agent_builder.add_node(METADATA_REVIEW_INTERRUPT_NODE, metadata_review_interrupt_node)
    agent_builder.add_node("rag_retrieval_node", rag_retrieval_node)
    agent_builder.add_node("teaching_design_planner", teaching_design_planner)
    agent_builder.add_node(TEACHING_PLAN_REVIEW_INTERRUPT_NODE, teaching_plan_review_interrupt_node)
    agent_builder.add_node("ppt_generate_node", ppt_generate_node)
    agent_builder.add_node("docx_generate_node", docx_generate_node)
    agent_builder.add_node("html_game_generate_node", html_generate_node)
    agent_builder.add_node("artifact_fan_in_node", artifact_fan_in_node)

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
            METADATA_REVIEW_INTERRUPT_NODE: METADATA_REVIEW_INTERRUPT_NODE,
            "follow_up_questioner": "follow_up_questioner",
        },
    )
    agent_builder.add_edge("follow_up_questioner", INTERRUPT_FOR_USERINPUT_NODE)
    agent_builder.add_edge(INTERRUPT_FOR_USERINPUT_NODE, "metadata_structer_node")
    # agent_builder.add_edge(METADATA_REVIEW_INTERRUPT_NODE, "rag_retrieval_node")
    agent_builder.add_edge("rag_retrieval_node", "teaching_design_planner")
    agent_builder.add_edge("teaching_design_planner", TEACHING_PLAN_REVIEW_INTERRUPT_NODE)
    # agent_builder.add_edge(TEACHING_PLAN_REVIEW_INTERRUPT_NODE, "ppt_generate_node")
    # agent_builder.add_edge(TEACHING_PLAN_REVIEW_INTERRUPT_NODE, "docx_generate_node")
    # agent_builder.add_edge(TEACHING_PLAN_REVIEW_INTERRUPT_NODE, "html_game_generate_node")
    agent_builder.add_edge("ppt_generate_node", "artifact_fan_in_node")
    agent_builder.add_edge("docx_generate_node", "artifact_fan_in_node")
    agent_builder.add_edge("html_game_generate_node", "artifact_fan_in_node")
    agent_builder.add_edge("artifact_fan_in_node", END)

    return agent_builder.compile(checkpointer=checkpointer)
