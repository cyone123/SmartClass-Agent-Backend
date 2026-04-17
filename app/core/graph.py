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
ARTIFACT_REVISION_CLARIFICATION_NODE = "artifact_revision_clarification_interrupt_node"

APPROVAL_INTERRUPT_NODES = {
    METADATA_REVIEW_INTERRUPT_NODE,
    TEACHING_PLAN_REVIEW_INTERRUPT_NODE,
    ARTIFACT_REVISION_CLARIFICATION_NODE,
}
RESUMABLE_INTERRUPT_NODES = {
    INTERRUPT_FOR_USERINPUT_NODE,
    *APPROVAL_INTERRUPT_NODES,
}
APPROVAL_STAGE_BY_NODE = {
    METADATA_REVIEW_INTERRUPT_NODE: "metadata_review",
    TEACHING_PLAN_REVIEW_INTERRUPT_NODE: "teaching_plan_review",
}

ARTIFACT_TYPE_LABELS = {
    "ppt": "课件 PPT",
    "docx": "教案文档",
    "html-game": "互动内容",
}
GENERATABLE_ARTIFACT_TYPES: tuple[Literal["ppt", "docx", "html-game"], ...] = (
    "ppt",
    "docx",
    "html-game",
)
TEACHING_PLAN_ARTIFACT_OPTIONS: tuple[dict[str, Any], ...] = (
    {"type": "ppt", "label": "课件 PPT", "selected": True},
    {"type": "docx", "label": "DOCX 教案", "selected": True},
    {"type": "html-game", "label": "HTML 互动演示", "selected": True},
)
ARTIFACT_FEEDBACK_BY_TYPE = {
    "ppt": "modify_ppt",
    "docx": "modify_lesson_plan",
    "html-game": "modify_game",
}
ARTIFACT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ppt": ("ppt", "课件", "幻灯", "幻灯片", "slide", "slides", "powerpoint"),
    "docx": ("docx", "教案", "文档", "word", "lesson plan"),
    "html-game": ("html", "互动", "游戏", "小游戏", "活动页", "网页", "activity"),
}
REVISION_VERBS = (
    "修改",
    "调整",
    "优化",
    "润色",
    "替换",
    "更新",
    "补充",
    "删掉",
    "重写",
    "改成",
    "改为",
    "change",
    "update",
    "edit",
    "revise",
    "fix",
)
REVISION_ALL_KEYWORDS = ("全部", "都", "所有", "一起", "all", "both", "三个")

class ConversationRoute(BaseModel):
    intent: Literal["normal_chat", "teaching_plan", "artifact_revision"] = Field(
        description="User intent for the conversation turn.",
    )
    artifact_targets: list[Literal["ppt", "docx", "html-game"]] = Field(
        default_factory=list,
        description="Suggested artifact targets when intent is artifact_revision.",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Whether the revision target remains ambiguous.",
    )


router = structured_output_llm.with_structured_output(
    ConversationRoute,
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


def _is_approve_action(user_input: Any) -> bool:
    return isinstance(user_input, Mapping) and user_input.get("action") == "approve"


def _build_approval_payload(
    stage: Literal["metadata_review", "teaching_plan_review", "artifact_revision_clarification"],
    *,
    metadata: Mapping[str, Any] | None = None,
    artifact_options: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if stage == "metadata_review":
        payload: dict[str, Any] = {
            "stage": stage,
            "title": "确认教学要素",
            "description": "已提取当前教学要素，请确认后继续生成教学设计方案。",
            "confirm_label": "确认并继续",
            "cancel_label": "取消并修改",
            "metadata": dict(metadata or {}),
        }
        return payload

    if stage == "teaching_plan_review":
        return {
            "stage": stage,
            "title": "确认教学设计方案",
            "description": "教学设计方案已生成，请确认是否继续生成课件、教案和互动内容。",
            "confirm_label": "确认并继续",
            "cancel_label": "取消并修改",
        }

    option_lines = []
    for artifact in artifact_options or ():
        artifact_type = str(artifact.get("type") or "")
        artifact_title = str(artifact.get("title") or ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type))
        option_lines.append(f"- {ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type)}：{artifact_title}")
    description = "你想修改哪个产物还不够明确。请直接输入更具体的修改要求，或者确认按当前会话里的全部产物一起修改。"
    if option_lines:
        description = f"{description}\n可选产物：\n" + "\n".join(option_lines)
    return {
        "stage": stage,
        "title": "确认修改目标",
        "description": description,
        "confirm_label": "默认修改全部",
        "cancel_label": "输入更具体要求",
    }


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
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return str(content)


def _latest_user_message_text(state: TeachingAssistantState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return _message_to_text(message).strip()
    return ""


def _artifact_catalog_summary(state: TeachingAssistantState) -> str:
    artifacts = state.get("artifact_catalog") or []
    if not artifacts:
        return "No ready artifacts exist in the current thread."
    lines = []
    for artifact in artifacts:
        artifact_type = str(artifact.get("type") or "")
        label = ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type)
        title = str(artifact.get("title") or label)
        revision_number = artifact.get("revision_number")
        revision_text = f" v{revision_number}" if revision_number else ""
        lines.append(f"- {label}{revision_text}: {title}")
    return "\n".join(lines)


def _looks_like_artifact_revision_request(message: str) -> bool:
    lowered = message.casefold()
    return any(keyword in lowered for keyword in REVISION_VERBS)


def _infer_revision_targets_from_text(
    message: str,
    artifact_catalog: Sequence[Mapping[str, Any]],
) -> tuple[str | None, list[str], bool]:
    available_types = [
        artifact_type
        for artifact_type in (
            str(item.get("type") or "")
            for item in artifact_catalog
        )
        if artifact_type in ARTIFACT_TYPE_LABELS
    ]
    unique_available_types = list(dict.fromkeys(available_types))
    lowered = message.casefold()

    if any(keyword in lowered for keyword in REVISION_ALL_KEYWORDS):
        return "modify_all", unique_available_types, False

    explicit_targets = [
        artifact_type
        for artifact_type, keywords in ARTIFACT_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords) and artifact_type in unique_available_types
    ]

    if explicit_targets:
        explicit_targets = list(dict.fromkeys(explicit_targets))
        if len(explicit_targets) > 1:
            return "modify_all", explicit_targets, False
        target_type = explicit_targets[0]
        return ARTIFACT_FEEDBACK_BY_TYPE[target_type], [target_type], False

    if len(unique_available_types) == 1:
        target_type = unique_available_types[0]
        return ARTIFACT_FEEDBACK_BY_TYPE[target_type], [target_type], False

    if unique_available_types:
        return None, [], True

    return None, [], False


def _pending_result_for_artifact_type(
    artifact_type: Literal["ppt", "docx", "html-game"],
) -> dict[str, Any]:
    return {
        "status": "pending",
        "artifact_id": None,
        "artifact_type": artifact_type,
        "title": None,
        "error": None,
    }


def _normalize_generation_targets(
    selected_types: Sequence[str] | None,
) -> list[Literal["ppt", "docx", "html-game"]]:
    if selected_types is None:
        return list(GENERATABLE_ARTIFACT_TYPES)
    return [
        artifact_type
        for artifact_type in dict.fromkeys(str(item) for item in selected_types)
        if artifact_type in GENERATABLE_ARTIFACT_TYPES
    ]


def _generation_result_reset_update(
    selected_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    normalized_targets = _normalize_generation_targets(selected_types)
    update: dict[str, Any] = {
        "generation_targets": normalized_targets,
        "revision_targets": [],
        "revision_source_artifacts": [],
        "revision_results": [],
        "user_feedback": None,
        "feedback_type": None,
    }
    if "ppt" in normalized_targets:
        update["ppt_result"] = _pending_result_for_artifact_type("ppt")
    if "docx" in normalized_targets:
        update["lesson_plan_result"] = _pending_result_for_artifact_type("docx")
    if "html-game" in normalized_targets:
        update["game_result"] = _pending_result_for_artifact_type("html-game")
    return update


def _revision_result_reset_update(
    selected_artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "revision_results": [],
    }
    target_types = {str(artifact.get("type") or "") for artifact in selected_artifacts}
    if "ppt" in target_types:
        update["ppt_result"] = _pending_result_for_artifact_type("ppt")
    if "docx" in target_types:
        update["lesson_plan_result"] = _pending_result_for_artifact_type("docx")
    if "html-game" in target_types:
        update["game_result"] = _pending_result_for_artifact_type("html-game")
    return update


def _result_key_for_artifact_type(artifact_type: str) -> str | None:
    return {
        "ppt": "ppt_result",
        "docx": "lesson_plan_result",
        "html-game": "game_result",
    }.get(artifact_type)


def metadata_review_interrupt_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "metadata_review", "running")
    _ = config
    user_input = interrupt(
        _build_approval_payload(
            "metadata_review",
            metadata=state.get("teaching_metadata") or {},
        )
    )
    if _is_approve_action(user_input):
        if reporter:
                reporter.emit("metadata_review", "success", detail="已确认教学要素")
        return Command(goto="rag_retrieval_node")
    if reporter:
                reporter.emit("metadata_review", "failed", detail="教学要素待修改")
    return Command(
        update=_build_resume_message_update(user_input),
        goto="metadata_structer_node",
    )


def intent_router_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "intent_recognition", "running")
    try:
        latest_message = _latest_user_message_text(state)
        artifact_catalog = state.get("artifact_catalog") or []
        if artifact_catalog and _looks_like_artifact_revision_request(latest_message):
            if reporter:
                reporter.emit("intent_recognition", "success", detail="识别为产物修改请求")
            return {"intent": "artifact_revision"}

        decision = router.invoke(
            [
                SystemMessage(
                    content=(
                        "You are an intent router for a teacher-facing workflow. "
                        "Output in json format and no any other character. "
                        "Return `artifact_revision` when the user is asking to edit, revise, update, or adjust an already-generated artifact in the same thread. "
                        "Return `teaching_plan` for lesson preparation, teaching design, courseware, lesson-plan, or interactive activity generation requests. "
                        "Return `normal_chat` for everything else. "
                        "Use the available artifact context below when deciding whether the user is referring to an existing artifact.\n\n"
                        f"Current thread artifacts:\n{_artifact_catalog_summary(state)}"
                    )
                ),
                *[msg for msg in state["messages"] if isinstance(msg, (HumanMessage, AIMessage))][-4:],
            ]
        )
        detail_by_intent = {
            "normal_chat": "识别为普通对话",
            "teaching_plan": "识别为教学设计请求",
            "artifact_revision": "识别为产物修改请求",
        }
        if reporter:
            reporter.emit("intent_recognition", "success", detail=detail_by_intent[decision.intent])
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
    if state.get("intent") == "artifact_revision":
        return "artifact_revision_router_node"
    return "normal_chat_node"


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
        "Output in json format and no any other character. "
        "Use only the user's provided information. Fill missing fields with None. "
        "Set `is_complete` to true only when the metadata is complete enough for retrieval and instructional design.\n"
        f"Current metadata: {current_metadata}"
    )
    start_time = time.perf_counter()
    try:
        response = metadata_extractor.invoke(
            [SystemMessage(content=system_prompt)]
            + [msg for msg in state["messages"] if isinstance(msg, HumanMessage)]
        )
        duration_ms = (time.perf_counter() - start_time) * 1000
        print(f"[metadata_structer_node] duration_ms={duration_ms:.2f} metadata={response}")
        if reporter:
            reporter.emit(
                "metadata_structuring",
                "success",
                detail=(
                    "已提取结构化教学要素"
                    if response.get("is_complete")
                    else "已提取结构化信息，仍需补充"
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
        return METADATA_REVIEW_INTERRUPT_NODE
    return "follow_up_questioner"


async def follow_up_questioner(state: TeachingAssistantState):
    system_prompt = (
        "你是教学助手中的主动追问节点。"
        "当教学要素不完整时，请基于当前缺失信息提出一个自然、简洁、关键的补充问题。"
        f"\n当前教学要素：{state.get('teaching_metadata')}"
    )
    response = await llm.ainvoke([SystemMessage(content=system_prompt)])
    return {"messages": [response]}


def interrupt_for_userinput(state: TeachingAssistantState):
    user_input = interrupt({"question": state["messages"][-1].content})
    if isinstance(user_input, dict):
        return {
            "messages": build_input_messages(
                str(user_input.get("message", "") or ""),
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
        "你是教师助手中的教学设计规划节点。"
        "请根据用户需求、结构化教学要素和检索上下文，输出一份完整、可执行的教学设计方案。"
        "这份结果会直接用于后续课件、教案和互动内容生成。\n"
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
    reporter = emit_progress(config, "teaching_plan_review", "running", detail="等待教师确认教学设计")
    user_input = interrupt(_build_approval_payload("teaching_plan_review"))
    if _is_approve_action(user_input):
        selected_types = _normalize_generation_targets(
            user_input.get("selected_artifact_types") if isinstance(user_input, Mapping) else None
        )
        if not selected_types:
            error_message = "请至少选择一个要生成的产物。"
            if reporter:
                reporter.emit("teaching_plan_review", "failed", detail=error_message)
            return Command(
                update={"messages": [AIMessage(content=error_message)]},
                goto=END,
            )
        if reporter:
            reporter.emit("teaching_plan_review", "success", detail="已确认教学设计")
        return Command(
            update=_generation_result_reset_update(selected_types),
            goto=_clean_goto_nodes([
                "ppt_generate_node" if "ppt" in selected_types else None,
                "docx_generate_node" if "docx" in selected_types else None,
                "html_game_generate_node" if "html-game" in selected_types else None,
            ]),
        )
    return Command(
        update=_build_resume_message_update(user_input),
        goto="teaching_design_planner",
    )


def artifact_revision_router_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(config, "artifact_revision_routing", "running")
    artifact_catalog = state.get("artifact_catalog") or []
    if not artifact_catalog:
        if reporter:
            reporter.emit("artifact_revision_routing", "failed", detail="当前会话没有可修改的产物")
        return Command(
            update={
                "messages": [
                    AIMessage(content="当前会话还没有可修改的产物。请先生成课件、教案或互动内容，再提出修改要求。")
                ]
            },
            goto=END,
        )

    latest_message = _latest_user_message_text(state)
    feedback_type, target_types, needs_clarification = _infer_revision_targets_from_text(
        latest_message,
        artifact_catalog,
    )

    if needs_clarification:
        if reporter:
            reporter.emit("artifact_revision_routing", "success", detail="修改目标不明确，等待用户澄清")
        return Command(goto=ARTIFACT_REVISION_CLARIFICATION_NODE)

    selected_artifacts = [
        artifact
        for artifact in artifact_catalog
        if str(artifact.get("type") or "") in target_types
    ]
    if not selected_artifacts:
        if reporter:
            reporter.emit("artifact_revision_routing", "failed", detail="未找到匹配的产物")
        return Command(
            update={
                "messages": [
                    AIMessage(content="我没有找到与你这次修改要求对应的现有产物。请说明要修改课件、教案还是互动内容。")
                ]
            },
            goto=END,
        )

    if reporter:
        reporter.emit(
            "artifact_revision_routing",
            "success",
            detail="已确定要修改的产物目标",
        )
    update = {
        "user_feedback": latest_message,
        "feedback_type": feedback_type or "modify_all",
        "revision_targets": selected_artifacts,
        "revision_source_artifacts": selected_artifacts,
        "iteration_count": int(state.get("iteration_count") or 0) + 1,
    }
    update.update(_revision_result_reset_update(selected_artifacts))
    if len(selected_artifacts) > 1:
        return Command(
            update=update,
            goto=_clean_goto_nodes([
                "ppt_revision_node" if any(item.get("type") == "ppt" for item in selected_artifacts) else None,
                "docx_revision_node" if any(item.get("type") == "docx" for item in selected_artifacts) else None,
                "html_game_revision_node" if any(item.get("type") == "html-game" for item in selected_artifacts) else None,
            ]),
        )

    target_type = str(selected_artifacts[0].get("type") or "")
    goto_map = {
        "ppt": "ppt_revision_node",
        "docx": "docx_revision_node",
        "html-game": "html_game_revision_node",
    }
    return Command(update=update, goto=goto_map[target_type])


def artifact_revision_clarification_interrupt_node(
    state: TeachingAssistantState,
    config: Optional[RunnableConfig] = None,
):
    reporter = emit_progress(
        config,
        "artifact_revision_routing",
        "running",
        detail="等待用户确认要修改的产物",
    )
    user_input = interrupt(
        _build_approval_payload(
            "artifact_revision_clarification",
            artifact_options=state.get("artifact_catalog") or [],
        )
    )
    if _is_approve_action(user_input):
        selected_artifacts = state.get("artifact_catalog") or []
        if reporter:
            reporter.emit("artifact_revision_routing", "success", detail="将默认修改当前全部产物")
        return Command(
            update={
                "feedback_type": "modify_all",
                "revision_targets": selected_artifacts,
                "revision_source_artifacts": selected_artifacts,
                "user_feedback": _latest_user_message_text(state),
                "iteration_count": int(state.get("iteration_count") or 0) + 1,
                **_revision_result_reset_update(selected_artifacts),
            },
            goto=_clean_goto_nodes([
                "ppt_revision_node" if any(item.get("type") == "ppt" for item in selected_artifacts) else None,
                "docx_revision_node" if any(item.get("type") == "docx" for item in selected_artifacts) else None,
                "html_game_revision_node" if any(item.get("type") == "html-game" for item in selected_artifacts) else None,
            ]),
        )
    return Command(
        update=_build_resume_message_update(user_input),
        goto="artifact_revision_router_node",
    )


def _result_summary_line(result: Mapping[str, Any] | None) -> str | None:
    if not result:
        return None
    artifact_type = str(result.get("artifact_type") or "")
    label = ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type)
    status = str(result.get("status") or "")
    if status == "ready":
        artifact_id = result.get("artifact_id")
        return f"{label}已完成，请在右侧资料去查看。产物 ID：{artifact_id}"
    if status == "failed":
        error = str(result.get("error") or "未知错误")
        return f"{label}处理失败：{error}"
    return None


# async def _artifact_fan_in_node_legacy(state: TeachingAssistantState, config: RunnableConfig | None = None):
#     reporter = emit_progress(config, "artifact_fan_in", "running")
#     summary_lines = [
#         line
#         for line in (
#             _result_summary_line(state.get("ppt_result")),
#             _result_summary_line(state.get("lesson_plan_result")),
#             _result_summary_line(state.get("game_result")),
#         )
#         if line
#     ]
#     if not summary_lines:
#         return {}

#     is_revision = bool(state.get("revision_source_artifacts"))
#     header = "产物修改结果如下：" if is_revision else "产物生成结果如下："
#     results = [
#         result
#         for result in (
#             state.get("ppt_result"),
#             state.get("lesson_plan_result"),
#             state.get("game_result"),
#         )
#         if isinstance(result, Mapping) and result.get("status") in {"ready", "failed"}
#     ]
#     if reporter:
#         reporter.emit("artifact_fan_in", "success", detail="已汇总产物处理结果")
#     return {
#         "revision_results": results,
#         "messages": [AIMessage(content=header + "\n" + "\n".join(f"- {line}" for line in summary_lines))],
#     }


async def artifact_fan_in_node(state: TeachingAssistantState, config: RunnableConfig | None = None):
    reporter = emit_progress(config, "artifact_fan_in", "running")
    is_revision = bool(state.get("revision_source_artifacts"))
    if is_revision:
        target_types = [
            str(artifact.get("type") or "")
            for artifact in (state.get("revision_source_artifacts") or [])
        ]
    else:
        target_types = _normalize_generation_targets(state.get("generation_targets"))

    results = [
        state.get(result_key)
        for result_key in (
            _result_key_for_artifact_type(artifact_type)
            for artifact_type in target_types
        )
        if result_key
    ]
    summary_lines = [
        line
        for line in (_result_summary_line(result) for result in results)
        if line
    ]
    if not summary_lines:
        return {}

    header = "产物修改结果如下：" if is_revision else "产物生成结果如下："
    finished_results = [
        result
        for result in results
        if isinstance(result, Mapping) and result.get("status") in {"ready", "failed"}
    ]
    if reporter:
        reporter.emit("artifact_fan_in", "success", detail="已汇总产物处理结果")
    return {
        "revision_results": finished_results,
        "messages": [AIMessage(content=header + "\n" + "\n".join(f"- {line}" for line in summary_lines))],
    }


def _clean_goto_nodes(nodes: Sequence[str | None]) -> list[str]:
    return [node for node in nodes if isinstance(node, str) and node]


def build_agent_graph(
    *,
    checkpointer: AsyncPostgresSaver,
    rag_runtime: RagRuntime,
    ppt_generate_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    docx_generate_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    html_generate_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    ppt_revision_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    docx_revision_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
    html_revision_node: Callable[[TeachingAssistantState, RunnableConfig | None], Awaitable[dict]],
):
    async def rag_retrieval_node(
        state: TeachingAssistantState,
        config: Optional[RunnableConfig] = None,
    ):
        reporter = emit_progress(config, "rag_retrieval", "running")
        try:
            query = _build_rag_query(state)
            result = await rag_runtime.retrieval(query, plan_id=state.get("plan_id"))
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
    agent_builder.add_node(INTERRUPT_FOR_USERINPUT_NODE, interrupt_for_userinput)
    agent_builder.add_node(METADATA_REVIEW_INTERRUPT_NODE, metadata_review_interrupt_node)
    agent_builder.add_node("rag_retrieval_node", rag_retrieval_node)
    agent_builder.add_node("teaching_design_planner", teaching_design_planner)
    agent_builder.add_node(TEACHING_PLAN_REVIEW_INTERRUPT_NODE, teaching_plan_review_interrupt_node)
    agent_builder.add_node("artifact_revision_router_node", artifact_revision_router_node)
    agent_builder.add_node(ARTIFACT_REVISION_CLARIFICATION_NODE, artifact_revision_clarification_interrupt_node)
    agent_builder.add_node("ppt_generate_node", ppt_generate_node)
    agent_builder.add_node("docx_generate_node", docx_generate_node)
    agent_builder.add_node("html_game_generate_node", html_generate_node)
    agent_builder.add_node("ppt_revision_node", ppt_revision_node)
    agent_builder.add_node("docx_revision_node", docx_revision_node)
    agent_builder.add_node("html_game_revision_node", html_revision_node)
    agent_builder.add_node("artifact_fan_in_node", artifact_fan_in_node)

    agent_builder.add_edge(START, "intent_router_node")
    agent_builder.add_conditional_edges(
        "intent_router_node",
        route_decision,
        {
            "normal_chat_node": "normal_chat_node",
            "metadata_structer_node": "metadata_structer_node",
            "artifact_revision_router_node": "artifact_revision_router_node",
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
    agent_builder.add_edge("rag_retrieval_node", "teaching_design_planner")
    agent_builder.add_edge("teaching_design_planner", TEACHING_PLAN_REVIEW_INTERRUPT_NODE)
    agent_builder.add_edge("ppt_generate_node", "artifact_fan_in_node")
    agent_builder.add_edge("docx_generate_node", "artifact_fan_in_node")
    agent_builder.add_edge("html_game_generate_node", "artifact_fan_in_node")
    agent_builder.add_edge("ppt_revision_node", "artifact_fan_in_node")
    agent_builder.add_edge("docx_revision_node", "artifact_fan_in_node")
    agent_builder.add_edge("html_game_revision_node", "artifact_fan_in_node")
    agent_builder.add_edge("artifact_fan_in_node", END)

    return agent_builder.compile(checkpointer=checkpointer)
