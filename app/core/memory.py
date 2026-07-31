from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.store.base import BaseStore, Item, SearchItem

from app.core.llm import memory_llm
from app.core.observability import (
    ObservationSink,
    RunContext,
    get_observation_sink,
    log_observation,
    observe_llm_call,
)

DEFAULT_USER_ID = "default-teacher"
PROFILE_MEMORY_KIND = "profile"
EXPERIENCE_MEMORY_KIND = "experience"
PROFILE_MEMORY_LIMIT = 100
EXPERIENCE_SUMMARY_LIMIT = 100
EXPERIENCE_SELECTION_LIMIT = 3
MEMORY_CONTEXT_MAX_CHARS = 6000
PROFILE_MEMORY_SIGNAL_PATTERNS = (
    r"请记住",
    r"记住",
    r"我最喜欢",
    r"我喜欢",
    r"我偏好",
    r"我习惯",
    r"我通常",
    r"我经常",
    r"我倾向",
    r"我更偏向",
    r"我重视",
    r"我强调",
    r"我使用",
    r"我用",
    r"我采用",
    r"我教授",
    r"我是.{0,20}(?:老师|教师)",
    r"\bi (?:prefer|teach|use|usually|often)\b",
    r"\bremember (?:that )?i\b",
    r"\bmy teaching\b",
)


class MemoryRuntimeContext(TypedDict, total=False):
    user_id: str


class MemoryItemPayload(TypedDict, total=False):
    title: str
    summary: str
    content: str
    tags: list[str]
    source_thread_id: str | None
    source_plan_id: int | None
    created_at: str
    updated_at: str
    kind: str


class MemorySearchSummary(TypedDict):
    id: str
    title: str
    summary: str
    tags: list[str]
    updated_at: str | None


MEMORY_REFLECTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_memory",
            "description": "Create a new durable long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short human-readable title for this memory.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief description used for future memory retrieval.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete memory content to save.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional short tags.",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "Update an existing long-term memory when the new information refines or replaces it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "existing_id": {
                        "type": "string",
                        "description": "The id of the existing memory to update.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Updated title.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Updated brief retrieval summary.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Updated complete memory content.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Updated optional short tags.",
                    },
                },
                "required": ["existing_id", "title", "content"],
            },
        },
    },
]
EXPERIENCE_SELECTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "select_experience_memories",
            "description": "Select reusable experience memories relevant to the current request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "At most 3 memory ids. Use an empty list if none are useful.",
                    }
                },
                "required": ["memory_ids"],
            },
        },
    }
]

profile_reflector = memory_llm.bind_tools(MEMORY_REFLECTION_TOOLS)
experience_reflector = memory_llm.bind_tools(MEMORY_REFLECTION_TOOLS)
experience_selector = memory_llm.bind_tools(EXPERIENCE_SELECTION_TOOLS)


def normalize_user_id(user_id: str | None) -> str:
    normalized = (user_id or "").strip()
    return normalized or DEFAULT_USER_ID


def profile_namespace(user_id: str | None) -> tuple[str, ...]:
    return ("users", normalize_user_id(user_id), "profile")


def experience_namespace(user_id: str | None) -> tuple[str, ...]:
    return ("users", normalize_user_id(user_id), "experiences")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def message_to_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def visible_conversation_text(messages: list[BaseMessage], *, limit: int = 12) -> str:
    visible = [message for message in messages if isinstance(message, (HumanMessage, AIMessage))][-limit:]
    lines: list[str] = []
    for message in visible:
        role = "Teacher" if isinstance(message, HumanMessage) else "Assistant"
        text = message_to_text(message).strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _item_to_memory_dict(item: SearchItem | Item) -> dict[str, Any]:
    value = dict(item.value or {})
    value.setdefault("id", item.key)
    value.setdefault("created_at", getattr(item, "created_at", None))
    value.setdefault("updated_at", getattr(item, "updated_at", None))
    if not isinstance(value.get("tags"), list):
        value["tags"] = []
    return value


def _memory_sort_key(item: SearchItem | Item) -> str:
    value = item.value or {}
    updated_at = value.get("updated_at")
    if isinstance(updated_at, str):
        return updated_at
    fallback = getattr(item, "updated_at", None)
    return fallback.isoformat() if fallback else ""


def _parse_tool_args(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return dict(args)
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _message_tool_calls(message: Any) -> list[dict[str, Any]]:
    tool_calls = getattr(message, "tool_calls", None) or []
    normalized: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        name = str(tool_call.get("name") or "")
        args = _parse_tool_args(tool_call.get("args"))
        if name:
            normalized.append({"name": name, "args": args})
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    raw_tool_calls = additional_kwargs.get("tool_calls") or []
    for tool_call in raw_tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") or {}
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "")
        args = _parse_tool_args(function.get("arguments"))
        if name:
            normalized.append({"name": name, "args": args})
    return normalized


def _first_tool_call(message: Any, allowed_names: set[str]) -> dict[str, Any] | None:
    for tool_call in _message_tool_calls(message):
        if tool_call["name"] in allowed_names:
            return tool_call
    return None


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_tags = value.split(",")
    elif isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = []
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()][:8]


async def search_memory_items(
    store: BaseStore | None,
    namespace: tuple[str, ...],
    *,
    limit: int = 100,
    query: str | None = None,
) -> list[dict[str, Any]]:
    if store is None:
        return []
    items = await store.asearch(namespace, query=query, limit=limit)
    sorted_items = sorted(items, key=_memory_sort_key, reverse=True)
    return [_item_to_memory_dict(item) for item in sorted_items]


async def get_memory_item(
    store: BaseStore | None,
    namespace: tuple[str, ...],
    key: str,
) -> dict[str, Any] | None:
    if store is None:
        return None
    item = await store.aget(namespace, key)
    return _item_to_memory_dict(item) if item is not None else None


async def put_memory_item(
    store: BaseStore,
    namespace: tuple[str, ...],
    *,
    value: dict[str, Any],
    key: str | None = None,
) -> dict[str, Any]:
    memory_key = key or uuid4().hex
    timestamp = now_iso()
    existing = await store.aget(namespace, memory_key)
    payload = dict(existing.value) if existing is not None else {}
    payload.update(value)
    payload["updated_at"] = timestamp
    payload.setdefault("created_at", timestamp)
    payload.setdefault("tags", [])
    await store.aput(namespace, memory_key, payload, index=False)
    payload["id"] = memory_key
    return payload


async def delete_memory_item(store: BaseStore, namespace: tuple[str, ...], key: str) -> None:
    await store.adelete(namespace, key)


def format_profile_memory_context(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["Long-term user profile and preferences:"]
    for memory in memories:
        title = str(memory.get("title") or "Preference")
        content = str(memory.get("content") or memory.get("summary") or "").strip()
        if content:
            lines.append(f"- {title}: {content}")
    return "\n".join(lines)[:MEMORY_CONTEXT_MAX_CHARS]


def experience_summaries(memories: list[dict[str, Any]]) -> list[MemorySearchSummary]:
    summaries: list[MemorySearchSummary] = []
    for memory in memories:
        memory_id = str(memory.get("id") or "")
        summary = str(memory.get("summary") or "").strip()
        if not memory_id or not summary:
            continue
        summaries.append(
            {
                "id": memory_id,
                "title": str(memory.get("title") or "Untitled memory"),
                "summary": summary,
                "tags": [str(tag) for tag in memory.get("tags") or []],
                "updated_at": memory.get("updated_at"),
            }
        )
    return summaries


def exact_title_experience_ids(
    summaries: list[MemorySearchSummary],
    conversation_text: str,
) -> list[str]:
    """Select unambiguous exact title matches before asking a model."""
    normalized_conversation = conversation_text.casefold()
    generic_titles = {"教学经验", "reusable experience", "experience", "untitled memory"}
    selected: list[str] = []
    for summary in summaries:
        title = str(summary.get("title") or "").strip()
        normalized_title = title.casefold()
        if (
            len(normalized_title) >= 3
            and normalized_title not in generic_titles
            and normalized_title in normalized_conversation
        ):
            selected.append(str(summary["id"]))
        if len(selected) >= EXPERIENCE_SELECTION_LIMIT:
            break
    return selected


def format_experience_memory_context(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    blocks = ["Relevant reusable teaching experiences:"]
    for memory in memories:
        title = str(memory.get("title") or "Reusable experience")
        content = str(memory.get("content") or memory.get("summary") or "").strip()
        if content:
            blocks.append(f"## {title}\n{content}")
    return "\n\n".join(blocks)[:MEMORY_CONTEXT_MAX_CHARS]


def build_memory_system_message(state: dict[str, Any]) -> SystemMessage | None:
    sections = [
        str(state.get("profile_memory_context") or "").strip(),
        str(state.get("experience_memory_context") or "").strip(),
    ]
    content = "\n\n".join(section for section in sections if section)
    if not content:
        return None
    return SystemMessage(
        content=(
            "Use the following long-term memory as background. "
            "Do not mention it unless it is naturally useful, and do not treat it as a replacement "
            "for explicit user instructions in the current conversation.\n\n"
            f"{content}"
        )
    )


def with_memory_context_messages(state: dict[str, Any]) -> list[BaseMessage]:
    memory_message = build_memory_system_message(state)
    if memory_message is None:
        return list(state.get("messages", []) or [])
    return [memory_message, *list(state.get("messages", []) or [])]


async def choose_relevant_experience_memories(
    *,
    store: BaseStore | None,
    user_id: str | None,
    state: dict[str, Any],
    run_context: RunContext | None = None,
    observation_sink: ObservationSink | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    if store is None:
        return "", []
    all_memories = await search_memory_items(
        store,
        experience_namespace(user_id),
        limit=EXPERIENCE_SUMMARY_LIMIT,
    )
    summaries = experience_summaries(all_memories)
    if not summaries:
        return "", []

    conversation_text = visible_conversation_text(list(state.get("messages", []) or []), limit=8)
    selected_ids = exact_title_experience_ids(summaries, conversation_text)
    prompt = [
        SystemMessage(
            content=(
                "You select reusable long-term teaching experiences for the current request. "
                "Call `select_experience_memories` with at most 3 memory ids. "
                "Use an empty list if the memories are not clearly useful."
            )
        ),
        HumanMessage(
            content=(
                "Current conversation:\n"
                f"{conversation_text}\n\n"
                "Available memory summaries JSON:\n"
                f"{json.dumps(summaries, ensure_ascii=False)}"
            )
        ),
    ]
    context = run_context or RunContext(run_id="memory", user_id=user_id, agent_name="memory")
    sink = observation_sink or get_observation_sink()
    if selected_ids:
        log_observation(
            "memory.experience_selection.exact_title",
            context=context.with_agent("memory"),
            sink=sink,
            status="success",
            fields={"selected_count": len(selected_ids)},
        )
    else:
        try:
            selection_message = await observe_llm_call(
                "llm.call",
                lambda: experience_selector.ainvoke(prompt),
                context=context.with_agent("memory"),
                sink=sink,
                model=experience_selector,
                messages=prompt,
                fields={"node": "experience_memory_selection_node"},
            )
        except Exception as exc:
            log_observation(
                "memory.experience_selection.skipped",
                context=context.with_agent("memory"),
                sink=sink,
                status="failed",
                fields={
                    "error_category": "memory_error",
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            return "", []
        tool_call = _first_tool_call(selection_message, {"select_experience_memories"})
        if tool_call is None:
            return "", []
        raw_ids = tool_call["args"].get("memory_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]

        selected_ids = [memory_id for memory_id in dict.fromkeys(str(item) for item in raw_ids) if memory_id]
        if not selected_ids:
            return "", []

    namespace = experience_namespace(user_id)
    selected: list[dict[str, Any]] = []
    for memory_id in selected_ids:
        memory = await get_memory_item(store, namespace, memory_id)
        if memory is not None:
            selected.append(memory)
        if len(selected) >= EXPERIENCE_SELECTION_LIMIT:
            break
    return format_experience_memory_context(selected), selected


def _existing_memory_prompt(memories: list[dict[str, Any]]) -> str:
    compact = [
        {
            "id": memory.get("id"),
            "title": memory.get("title"),
            "summary": memory.get("summary"),
            "content": memory.get("content"),
            "tags": memory.get("tags") or [],
        }
        for memory in memories
    ]
    return json.dumps(compact, ensure_ascii=False)


def should_reflect_profile_memory(state: dict[str, Any]) -> bool:
    """Conservatively require an explicit stable-profile signal before model reflection."""
    user_text = "\n".join(
        str(message.content)
        for message in list(state.get("messages", []) or [])[-8:]
        if isinstance(message, HumanMessage)
    ).casefold()
    return any(re.search(pattern, user_text, flags=re.IGNORECASE) for pattern in PROFILE_MEMORY_SIGNAL_PATTERNS)


async def reflect_profile_memory(
    *,
    store: BaseStore | None,
    user_id: str | None,
    state: dict[str, Any],
    run_context: RunContext | None = None,
    observation_sink: ObservationSink | None = None,
) -> dict[str, Any] | None:
    if store is None:
        return None
    if not should_reflect_profile_memory(state):
        log_observation(
            "memory.profile_reflection.skipped",
            context=(run_context or RunContext(run_id="memory", user_id=user_id, agent_name="memory")),
            sink=observation_sink or get_observation_sink(),
            status="success",
            fields={"reason": "no_stable_profile_signal"},
        )
        return None
    namespace = profile_namespace(user_id)
    existing = await search_memory_items(store, namespace, limit=PROFILE_MEMORY_LIMIT)
    prompt = [
        SystemMessage(
            content=(
                "你负责从对话中提取用户画像、用户偏好或用户明确要求记住的内容，并保存为长期记忆。"
                "仅保存稳定的用户偏好、明确要求记住的某项内容、教学风格偏好、重复出现的约束条件，或与未来教学工作相关的用户画像信息。"
                "除非用户明确要求记住，否则不要保存临时的课程内容信息。"
                "不要保存学校全名、住址、联系方式、证件号、健康信息、家庭收入或社会经济背景；"
                "只保留完成未来教学任务真正需要的最小化摘要。"
                "对用户明确使用的课程名、教学法和专业术语，保留原始语言和大小写。"
                "如果不应写入任何长期记忆，则不要调用任何工具。"
                "当新信息替换或完善了已有记忆时，使用 existing_id 调用 `update_memory`；"
                "否则调用 `create_memory`。"
            )
        ),
        HumanMessage(
            content=(
                "Existing profile memories JSON:\n"
                f"{_existing_memory_prompt(existing)}\n\n"
                "Recent conversation:\n"
                f"{visible_conversation_text(list(state.get('messages', []) or []), limit=8)}"
            )
        ),
    ]
    context = run_context or RunContext(run_id="memory", user_id=user_id, agent_name="memory")
    sink = observation_sink or get_observation_sink()
    try:
        response = await observe_llm_call(
            "llm.call",
            lambda: profile_reflector.ainvoke(prompt),
            context=context.with_agent("memory"),
            sink=sink,
            model=profile_reflector,
            messages=prompt,
            fields={"node": "profile_memory_reflection_node"},
        )
    except Exception as exc:
        log_observation(
            "memory.profile_reflection.skipped",
            context=context.with_agent("memory"),
            sink=sink,
            status="failed",
            fields={
                "error_category": "memory_error",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
        )
        return None
    return await apply_memory_tool_call(
        store,
        namespace,
        _first_tool_call(response, {"create_memory", "update_memory"}),
        kind=PROFILE_MEMORY_KIND,
        source_thread_id=None,
        source_plan_id=None,
    )


async def reflect_experience_memory(
    *,
    store: BaseStore | None,
    user_id: str | None,
    state: dict[str, Any],
    thread_id: str | None,
    plan_id: int | None,
    run_context: RunContext | None = None,
    observation_sink: ObservationSink | None = None,
) -> dict[str, Any] | None:
    if store is None:
        return None
    namespace = experience_namespace(user_id)
    existing = await search_memory_items(store, namespace, limit=EXPERIENCE_SUMMARY_LIMIT)
    prompt = [
        SystemMessage(
            content=(
                "判断这段已完成的对话是否包含可复用的教学经验。"
                "仅保存可复用的策略、活动模式、提示优化、生成的成果、课程设计或可持续的工作流程观察结果等可能对未来的教学环节有所帮助的内容。"
                "如果对话未完成，或不包含任何可复用的教学经验，则不要保存。"
                "如果无需写入可复用的记忆，则不要调用任何工具。"
                "如果是对已有经验的优化，则使用 `update_memory` 并指定一个现有的 ID；"
                "否则，调用 `create_memory`。"
            )
        ),
        HumanMessage(
            content=(
                "Existing experience memories JSON:\n"
                f"{_existing_memory_prompt(existing)}\n\n"
                "Completed conversation:\n"
                f"{visible_conversation_text(list(state.get('messages', []) or []), limit=14)}\n\n"
                "Teaching metadata JSON:\n"
                f"{json.dumps(state.get('teaching_metadata') or {}, ensure_ascii=False, default=str)}\n\n"
                "Artifact results JSON:\n"
                f"{json.dumps(state.get('revision_results') or [], ensure_ascii=False, default=str)}"
            )
        ),
    ]
    context = run_context or RunContext(
        run_id="memory",
        thread_id=thread_id,
        plan_id=plan_id,
        user_id=user_id,
        agent_name="memory",
    )
    sink = observation_sink or get_observation_sink()
    try:
        response = await observe_llm_call(
            "llm.call",
            lambda: experience_reflector.ainvoke(prompt),
            context=context.with_agent("memory"),
            sink=sink,
            model=experience_reflector,
            messages=prompt,
            fields={"node": "experience_memory_reflection_node"},
        )
    except Exception as exc:
        log_observation(
            "memory.experience_reflection.skipped",
            context=context.with_agent("memory"),
            sink=sink,
            status="failed",
            fields={
                "error_category": "memory_error",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
        )
        return None
    return await apply_memory_tool_call(
        store,
        namespace,
        _first_tool_call(response, {"create_memory", "update_memory"}),
        kind=EXPERIENCE_MEMORY_KIND,
        source_thread_id=thread_id,
        source_plan_id=plan_id,
    )


async def apply_memory_tool_call(
    store: BaseStore,
    namespace: tuple[str, ...],
    tool_call: dict[str, Any] | None,
    *,
    kind: str,
    source_thread_id: str | None,
    source_plan_id: int | None,
) -> dict[str, Any] | None:
    if tool_call is None:
        return None
    args = tool_call["args"]
    content = sanitize_memory_text(str(args.get("content") or args.get("summary") or ""))
    if not content:
        return None
    key = str(args.get("existing_id") or "").strip() if tool_call["name"] == "update_memory" else None
    if key == "":
        key = None
    value: MemoryItemPayload = {
        "kind": kind,
        "title": sanitize_memory_text(str(args.get("title") or "Memory")),
        "summary": sanitize_memory_text(str(args.get("summary") or content[:240])),
        "content": content,
        "tags": [sanitize_memory_text(tag) for tag in _normalize_tags(args.get("tags"))],
        "source_thread_id": source_thread_id,
        "source_plan_id": source_plan_id,
    }
    return await put_memory_item(store, namespace, value=value, key=key)


def sanitize_memory_text(value: str) -> str:
    """Minimize common direct identifiers and sensitive socioeconomic details."""
    sanitized = value.strip()
    replacements = (
        (r"(?<!\d)1[3-9]\d{9}(?!\d)", "[已移除手机号]"),
        (r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[已移除邮箱]"),
        (r"(?<!\d)\d{17}[\dXx](?!\d)", "[已移除证件号]"),
        (r"[\u4e00-\u9fff]{2,20}(?:中学|小学|大学|学院)", "某学校"),
        (
            r"(?:来自|均来自|都是来自)?(?:富裕|贫困|低收入|高收入|中产)(?:家庭|背景|群体)?",
            "具有不同家庭背景",
        ),
    )
    for pattern, replacement in replacements:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized.strip()
