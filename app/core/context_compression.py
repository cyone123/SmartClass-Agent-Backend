from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)

from app.config import (
    get_context_compression_enabled,
    get_context_compression_keep_recent_turns,
    get_context_compression_max_output_tokens,
    get_context_compression_max_preface_chars,
    get_context_compression_trigger_tokens,
)
from app.core.llm import get_context_compression_llm
from app.core.observability import (
    ObservationSink,
    RunContext,
    categorize_error,
    log_observation,
    observe_llm_call,
)

COMPRESSED_CONTEXT_MARKER = "[SmartClass compressed thread context]"
COMPRESSED_CONTEXT_FLAG = "smartclass_context_compressed"
CHAR_TOKEN_RATIO = 4

SkipReason = Literal[
    "disabled",
    "no_thread",
    "pending_approval",
    "resumable_interrupt",
    "below_threshold",
    "too_few_messages",
    "missing_message_ids",
]


@dataclass(frozen=True)
class CompressionSettings:
    enabled: bool = field(default_factory=get_context_compression_enabled)
    trigger_tokens: int = field(default_factory=get_context_compression_trigger_tokens)
    keep_recent_turns: int = field(default_factory=get_context_compression_keep_recent_turns)
    max_output_tokens: int = field(default_factory=get_context_compression_max_output_tokens)
    max_preface_chars: int = field(default_factory=get_context_compression_max_preface_chars)


@dataclass(frozen=True)
class CompressionPlan:
    should_compress: bool
    reason: str
    estimated_tokens: int
    message_count: int
    retained_message_count: int = 0
    compressible_message_count: int = 0
    retained_messages: tuple[BaseMessage, ...] = ()
    compressible_messages: tuple[BaseMessage, ...] = ()


@dataclass(frozen=True)
class CompressionResult:
    status: Literal["skipped", "success", "failed"]
    reason: str
    update: dict[str, list[BaseMessage]] | None = None
    estimated_tokens_before: int = 0
    estimated_tokens_after: int = 0
    message_count_before: int = 0
    message_count_after: int = 0
    retained_message_count: int = 0
    removed_message_count: int = 0
    summary_size: int = 0
    duration_ms: int = 0


def is_compressed_context_message(message: Any) -> bool:
    if not isinstance(message, SystemMessage):
        return False
    if (getattr(message, "additional_kwargs", {}) or {}).get(COMPRESSED_CONTEXT_FLAG) is True:
        return True
    return message_to_text(message).lstrip().startswith(COMPRESSED_CONTEXT_MARKER)


def message_to_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def estimate_message_tokens(messages: Sequence[BaseMessage], model: Any | None = None) -> int:
    if model is not None:
        token_counter = getattr(model, "get_num_tokens_from_messages", None)
        if callable(token_counter):
            try:
                return int(token_counter(list(messages)))
            except Exception:
                pass

    total_chars = 0
    for message in messages:
        role_overhead = 8
        total_chars += role_overhead + len(message_to_text(message))
    return max(1, (total_chars + CHAR_TOKEN_RATIO - 1) // CHAR_TOKEN_RATIO)


def _recent_turn_cutoff(messages: Sequence[BaseMessage], keep_recent_turns: int) -> int:
    human_indexes = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, HumanMessage) and not is_compressed_context_message(message)
    ]
    if len(human_indexes) <= keep_recent_turns:
        return 0
    return human_indexes[-keep_recent_turns]


def build_compression_plan(
    state: Mapping[str, Any],
    *,
    settings: CompressionSettings | None = None,
    model: Any | None = None,
) -> CompressionPlan:
    settings = settings or CompressionSettings()
    messages = tuple(
        message
        for message in state.get("messages", []) or []
        if isinstance(message, BaseMessage)
    )
    estimated_tokens = estimate_message_tokens(messages, model=model)
    if not settings.enabled:
        return CompressionPlan(False, "disabled", estimated_tokens, len(messages))
    if estimated_tokens < settings.trigger_tokens:
        return CompressionPlan(False, "below_threshold", estimated_tokens, len(messages))

    cutoff = _recent_turn_cutoff(messages, settings.keep_recent_turns)
    if cutoff <= 0:
        return CompressionPlan(False, "too_few_messages", estimated_tokens, len(messages))

    compressible = tuple(messages[:cutoff])
    retained = tuple(messages[cutoff:])
    if not compressible:
        return CompressionPlan(False, "too_few_messages", estimated_tokens, len(messages))
    if any(not getattr(message, "id", None) for message in messages):
        return CompressionPlan(
            False,
            "missing_message_ids",
            estimated_tokens,
            len(messages),
            retained_message_count=len(retained),
            compressible_message_count=len(compressible),
            retained_messages=retained,
            compressible_messages=compressible,
        )
    return CompressionPlan(
        True,
        "threshold_reached",
        estimated_tokens,
        len(messages),
        retained_message_count=len(retained),
        compressible_message_count=len(compressible),
        retained_messages=retained,
        compressible_messages=compressible,
    )


def _truncate(value: str, limit: int) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "\n...[truncated]"


def _json_block(value: Any, *, limit: int) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except TypeError:
        text = str(value)
    return _truncate(text, limit)


def build_structured_state_preface(
    state: Mapping[str, Any],
    *,
    max_chars: int | None = None,
) -> str:
    max_chars = max_chars or get_context_compression_max_preface_chars()
    section_limits = {
        "Teaching metadata": 1800,
        "Teaching design plan": 1800,
        "RAG digest": 1800,
        "Artifact state": 1600,
        "Revision state": 1600,
    }
    sections: list[str] = []

    metadata = _json_block(state.get("teaching_metadata"), limit=section_limits["Teaching metadata"])
    if metadata:
        sections.append(f"## Teaching metadata\n{metadata}")

    design_plan = str(state.get("teaching_design_plan") or "").strip()
    if design_plan:
        sections.append(f"## Teaching design plan\n{_truncate(design_plan, section_limits['Teaching design plan'])}")

    rag_payload = {
        "rag_context": str(state.get("rag_context") or "").strip(),
        "rag_results": state.get("rag_results") or [],
    }
    rag_digest = _json_block(rag_payload, limit=section_limits["RAG digest"])
    if rag_digest and rag_payload != {"rag_context": "", "rag_results": []}:
        sections.append(f"## RAG digest\n{rag_digest}")

    artifact_payload = {
        "artifact_catalog": state.get("artifact_catalog") or [],
        "ppt_result": state.get("ppt_result"),
        "lesson_plan_result": state.get("lesson_plan_result"),
        "game_result": state.get("game_result"),
    }
    artifact_digest = _json_block(artifact_payload, limit=section_limits["Artifact state"])
    if artifact_digest and any(artifact_payload.values()):
        sections.append(f"## Artifact state\n{artifact_digest}")

    revision_payload = {
        "user_feedback": state.get("user_feedback"),
        "feedback_type": state.get("feedback_type"),
        "revision_targets": state.get("revision_targets") or [],
        "revision_source_artifacts": state.get("revision_source_artifacts") or [],
        "revision_results": state.get("revision_results") or [],
    }
    revision_digest = _json_block(revision_payload, limit=section_limits["Revision state"])
    if revision_digest and any(revision_payload.values()):
        sections.append(f"## Revision state\n{revision_digest}")

    if not sections:
        return "No structured SmartClass state is currently available."
    return _truncate("\n\n".join(sections), max_chars)


def _format_conversation(messages: Sequence[BaseMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            role = "Teacher"
        elif isinstance(message, AIMessage):
            role = "Assistant"
        elif isinstance(message, SystemMessage):
            role = "System"
        else:
            role = message.__class__.__name__
        text = _truncate(message_to_text(message), 3000)
        if text:
            lines.append(f"{role}: {text}")
    return "\n\n".join(lines)


def build_compression_prompt(
    state: Mapping[str, Any],
    plan: CompressionPlan,
    *,
    settings: CompressionSettings | None = None,
) -> list[BaseMessage]:
    settings = settings or CompressionSettings()
    preface = build_structured_state_preface(state, max_chars=settings.max_preface_chars)
    conversation = _format_conversation(plan.compressible_messages)
    retained = _format_conversation(plan.retained_messages[-4:])
    return [
        SystemMessage(
            content=(
                "你是 SmartClass 的短期上下文压缩器。只输出压缩后的线程上下文，"
                "不要编造结构化状态中不存在的信息，不要保存完整敏感文本。"
                "保留教学目标、已确认决策、用户约束、未解决问题、附件/RAG/产物要点。"
            )
        ),
        HumanMessage(
            content=(
                f"Structured SmartClass state preface:\n{preface}\n\n"
                f"Conversation to compress:\n{conversation or '<empty>'}\n\n"
                f"Recent raw turns that will remain outside the summary:\n{retained or '<empty>'}\n\n"
                "Return a concise Chinese summary with sections: "
                "对话目标、已确认事实、关键约束、未解决问题、后续注意事项。"
            )
        ),
    ]


def build_compressed_message(
    state: Mapping[str, Any],
    summary: str,
    *,
    settings: CompressionSettings | None = None,
) -> SystemMessage:
    settings = settings or CompressionSettings()
    preface = build_structured_state_preface(state, max_chars=settings.max_preface_chars)
    normalized_summary = _truncate(summary.strip(), settings.max_output_tokens * CHAR_TOKEN_RATIO)
    content = (
        f"{COMPRESSED_CONTEXT_MARKER}\n"
        "This system message is hidden from the teacher-facing chat UI and is used only as future model context.\n\n"
        "# Structured SmartClass State\n"
        f"{preface}\n\n"
        "# Compressed Conversation History\n"
        f"{normalized_summary or 'No older conversation summary was produced.'}"
    )
    return SystemMessage(
        id=f"context-compression-{uuid4().hex}",
        content=content,
        additional_kwargs={COMPRESSED_CONTEXT_FLAG: True},
    )


def build_replacement_update(
    messages: Sequence[BaseMessage],
    compressed_message: SystemMessage,
    retained_messages: Sequence[BaseMessage],
) -> dict[str, list[BaseMessage]]:
    removals = [RemoveMessage(id=str(message.id)) for message in messages if getattr(message, "id", None)]
    return {"messages": [*removals, compressed_message, *retained_messages]}


async def compress_state_messages(
    state: Mapping[str, Any],
    *,
    context: RunContext,
    sink: ObservationSink | None,
    settings: CompressionSettings | None = None,
    model: Any | None = None,
    on_compression_started: Any | None = None,
) -> CompressionResult:
    settings = settings or CompressionSettings()
    plan = build_compression_plan(state, settings=settings, model=model)
    base_fields = {
        "estimated_tokens": plan.estimated_tokens,
        "threshold_tokens": settings.trigger_tokens,
        "message_count": plan.message_count,
        "retained_message_count": plan.retained_message_count,
        "compressible_message_count": plan.compressible_message_count,
        "decision": "compress" if plan.should_compress else "skip",
        "reason": plan.reason,
    }
    log_observation(
        "context.compression.checked",
        context=context.with_agent("context_compression"),
        sink=sink,
        status="success",
        fields=base_fields,
    )
    if not plan.should_compress:
        log_observation(
            "context.compression.skipped",
            context=context.with_agent("context_compression"),
            sink=sink,
            status="success",
            fields=base_fields,
        )
        return CompressionResult(
            status="skipped",
            reason=plan.reason,
            estimated_tokens_before=plan.estimated_tokens,
            message_count_before=plan.message_count,
            retained_message_count=plan.retained_message_count,
        )

    started = time.perf_counter()
    log_observation(
        "context.compression.started",
        context=context.with_agent("context_compression"),
        sink=sink,
        status="running",
        fields=base_fields,
    )
    if callable(on_compression_started):
        on_compression_started(plan)
    try:
        model = model or get_context_compression_llm(streaming=False)
        prompt_messages = build_compression_prompt(state, plan, settings=settings)
        response = await observe_llm_call(
            "llm.call",
            lambda: asyncio.wait_for(
                model.ainvoke(prompt_messages),
                timeout=getattr(model, "request_timeout", None) or None,
            ),
            context=context.with_agent("context_compression"),
            sink=sink,
            model=model,
            messages=prompt_messages,
            fields={"node": "context_compression"},
        )
        summary = message_to_text(response) if isinstance(response, BaseMessage) else str(response)
        compressed_message = build_compressed_message(state, summary, settings=settings)
        all_messages = tuple(
            message
            for message in state.get("messages", []) or []
            if isinstance(message, BaseMessage)
        )
        update = build_replacement_update(all_messages, compressed_message, plan.retained_messages)
        after_messages = (compressed_message, *plan.retained_messages)
        estimated_after = estimate_message_tokens(after_messages, model=model)
        duration_ms = int((time.perf_counter() - started) * 1000)
        fields = {
            **base_fields,
            "duration_ms": duration_ms,
            "estimated_tokens_before": plan.estimated_tokens,
            "estimated_tokens_after": estimated_after,
            "message_count_before": len(all_messages),
            "message_count_after": len(after_messages),
            "removed_message_count": len(all_messages) - len(after_messages),
            "summary_size": len(message_to_text(compressed_message)),
        }
        log_observation(
            "context.compression.completed",
            context=context.with_agent("context_compression"),
            sink=sink,
            status="success",
            fields=fields,
        )
        return CompressionResult(
            status="success",
            reason="compressed",
            update=update,
            estimated_tokens_before=plan.estimated_tokens,
            estimated_tokens_after=estimated_after,
            message_count_before=len(all_messages),
            message_count_after=len(after_messages),
            retained_message_count=plan.retained_message_count,
            removed_message_count=len(all_messages) - len(after_messages),
            summary_size=len(message_to_text(compressed_message)),
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_observation(
            "context.compression.failed",
            context=context.with_agent("context_compression"),
            sink=sink,
            status="failed",
            fields={
                **base_fields,
                "duration_ms": duration_ms,
                "error_category": categorize_error(exc),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
        )
        return CompressionResult(
            status="failed",
            reason=exc.__class__.__name__,
            estimated_tokens_before=plan.estimated_tokens,
            message_count_before=plan.message_count,
            retained_message_count=plan.retained_message_count,
            duration_ms=duration_ms,
        )
