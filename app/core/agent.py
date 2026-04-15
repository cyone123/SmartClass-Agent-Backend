from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from fastapi import Request
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    FilesystemFileSearchMiddleware,
    HostExecutionPolicy,
    ModelRequest,
    ModelResponse,
    ShellToolMiddleware,
    ToolRetryMiddleware,
)
from langchain.messages import SystemMessage
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.config import get_backend_root
from app.core.graph import build_agent_graph, build_input_messages
from app.core.llm import get_model, get_small_model
from app.core.progress import (
    ProgressReporter,
    ProgressTracker,
    register_progress_reporter,
    unregister_progress_reporter,
)
from app.core.rag import RagRuntime
from app.core.skills import SkillRegistry, SkillToolset, create_skill_registry
from app.core.state import SubAgentResult, TeachingAssistantState
from app.core.workspace import WorkspaceToolset, get_workspace_paths
from app.dependencies.db import AsyncSessionLocal, close_agent_checkpointer, init_agent_checkpointer
from app.services import artifact_service

ArtifactType = Literal["ppt", "docx", "html-game"]
ArtifactEventEmitter = Callable[[dict[str, Any]], None]

INTERRUPT_FOR_USERINPUT_NODE = "interrupt_for_userinput"
ROOT_STREAMING_NODES = {"normal_chat_node", "follow_up_questioner", "teaching_design_planner"}
SUGGESTION_COUNT = 3
SUGGESTION_CONTEXT_WINDOW = 6
WORKSPACE_TOOL_NAMES = {
    "list_workspace_files",
    "read_workspace_file",
    "write_workspace_file",
    "run_workspace_code",
}
BLOCKED_SHELL_PATTERN = re.compile(
    r"(?i)(^|\s)(python|python3|py|node|npm|npx|pip|pip3|pnpm|yarn|uv)\b"
)
ARTIFACT_STEP_KEYS: dict[ArtifactType, str] = {
    "ppt": "ppt_generation",
    "docx": "lesson_plan_generation",
    "html-game": "game_generation",
}
ARTIFACT_STATE_KEYS: dict[ArtifactType, str] = {
    "ppt": "ppt_result",
    "docx": "lesson_plan_result",
    "html-game": "game_result",
}
ARTIFACT_ALLOWED_EXTENSIONS: dict[ArtifactType, tuple[str, ...]] = {
    "ppt": (".pptx",),
    "docx": (".docx",),
    "html-game": (".html",),
}


class SkillAwareAgentState(AgentState[Any], total=False):
    active_skills: list[str]


def get_thread_config(
    thread_id: str | None,
    *,
    run_id: str | None = None,
    progress_reporter: ProgressReporter | None = None,
    artifact_event_emitter: ArtifactEventEmitter | None = None,
) -> RunnableConfig:
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
    }
    if run_id is not None:
        configurable["run_id"] = run_id
    if progress_reporter is not None:
        configurable["progress_reporter"] = progress_reporter
    if artifact_event_emitter is not None:
        configurable["artifact_event_emitter"] = artifact_event_emitter
    return {"configurable": configurable}


def _get_configurable_value(config: RunnableConfig | None, key: str) -> Any:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    return configurable.get(key)


def _get_artifact_event_emitter(config: RunnableConfig | None) -> ArtifactEventEmitter | None:
    emitter = _get_configurable_value(config, "artifact_event_emitter")
    return emitter if callable(emitter) else None


def _message_to_text(message: AnyMessage) -> str:
    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                item_text = item.get("text")
                if isinstance(item_text, str):
                    text_parts.append(item_text)
        return "".join(text_parts)

    return str(content)


def get_final_response_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _message_to_text(message).strip()
    return ""


def _normalize_suggestion_text(value: str) -> str:
    text = re.sub(r"^\s*[-*]+\s*", "", value or "")
    text = re.sub(r"^\s*\d+[.)、]\s*", "", text)
    text = text.strip().strip("\"'")
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_suggestions(values: list[str] | None) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalize_suggestion_text(item)
        if not text:
            continue
        dedupe_key = text.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(text)

    return normalized[:SUGGESTION_COUNT]


def _split_suggestion_lines(value: str) -> list[str]:
    if not value:
        return []

    raw_lines = [
        line.strip()
        for line in re.split(r"\r?\n+", value)
        if line.strip()
    ]
    return raw_lines[: max(SUGGESTION_COUNT * 2, SUGGESTION_COUNT)]


def _build_suggestion_conversation(messages: list[AnyMessage]) -> list[str]:
    visible_messages = [
        message
        for message in messages
        if isinstance(message, (HumanMessage, AIMessage)) and not isinstance(message, ToolMessage)
    ]
    conversation_slice = visible_messages[-SUGGESTION_CONTEXT_WINDOW:]

    conversation_lines: list[str] = []
    for message in conversation_slice:
        role = "用户" if isinstance(message, HumanMessage) else "AI"
        text = _message_to_text(message).strip()
        if text:
            conversation_lines.append(f"{role}: {text}")
    return conversation_lines


def _default_subagent_result(artifact_type: ArtifactType, *, status: str = "pending") -> SubAgentResult:
    return {
        "status": status,
        "artifact_id": None,
        "artifact_type": artifact_type,
        "title": None,
        "error": None,
    }


def _success_subagent_result(artifact_type: ArtifactType, *, artifact_id: int, title: str) -> SubAgentResult:
    return {
        "status": "ready",
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "title": title,
        "error": None,
    }


def _failed_subagent_result(
    artifact_type: ArtifactType,
    *,
    artifact_id: int | None = None,
    title: str | None = None,
    error: str,
) -> SubAgentResult:
    return {
        "status": "failed",
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "title": title,
        "error": error,
    }


def _artifact_payload(record: Any) -> dict[str, Any]:
    return artifact_service.serialize_artifact(record)


def _artifact_display_name(artifact_type: ArtifactType) -> str:
    return {
        "ppt": "课件",
        "docx": "教案",
        "html-game": "互动内容",
    }[artifact_type]


class SkillPromptMiddleware(AgentMiddleware):
    """Inject skill metadata into the agent system prompt."""

    def __init__(self, registry: SkillRegistry) -> None:
        skill_lines = [
            f"- **{skill.name}**: {skill.description}"
            for skill in registry.list_metadata()
        ]
        self.skills_prompt = "\n".join(skill_lines)

    def _inject_skill_catalog(self, request: ModelRequest) -> ModelRequest:
        skills_addendum = (
            f"\n\n## Available Skills\n\n{self.skills_prompt}\n\n"
            "Only the metadata above is preloaded. When a request matches a skill, "
            "use `load_skill` to read its instructions. Then use `read_skill_resource` "
            "or `run_skill_script` when you need to read relevant resources or run a skill script. "
            "Only use workspace code tools after a skill is loaded and only when "
            "that skill needs coding operations. Use workspace code tools for "
            "temporary Python or JavaScript files, `run_skill_script` for scripts "
            "that already ship with the skill, and reserve `shell` for non-code "
            "system commands only. When calling `run_skill_script`, pass "
            "`script_args` as a string array."
        )

        if request.system_message is None:
            new_system_message = SystemMessage(content=skills_addendum.strip())
        else:
            new_content = list(request.system_message.content_blocks) + [
                {"type": "text", "text": skills_addendum}
            ]
            new_system_message = SystemMessage(content=new_content)
        return request.override(system_message=new_system_message)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._inject_skill_catalog(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return await handler(self._inject_skill_catalog(request))


class SkillExecutionPolicyMiddleware(AgentMiddleware[SkillAwareAgentState, Any, Any]):
    """Track active skills and guard skill-aware execution tools."""

    state_schema = SkillAwareAgentState

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def _get_active_skill_names(self, state: SkillAwareAgentState | dict[str, Any]) -> list[str]:
        values = state.get("active_skills", []) or []
        return [str(value) for value in values if isinstance(value, str)]

    def _get_authorized_skills(
        self,
        state: SkillAwareAgentState | dict[str, Any],
        *,
        tool_name: str,
    ) -> list[str]:
        active_skill_names = self._get_active_skill_names(state)
        return [
            skill_name
            for skill_name in active_skill_names
            if self.registry.skill_allows_tool(skill_name, tool_name)
        ]

    def _build_active_skill_section(self, active_skill_names: list[str]) -> str:
        if not active_skill_names:
            return ""

        lines = ["\n\n## Active Skills"]
        for skill_name in active_skill_names:
            skill = self.registry.get_skill(skill_name)
            allowed_tools = ", ".join(skill.allowed_tools) if skill.allowed_tools else "none"
            compatibility = skill.compatibility or "none"
            lines.append(
                f"- **{skill.name}**: allowed tools = {allowed_tools}; "
                f"compatibility = {compatibility}"
            )
        lines.append(
            "If you need temporary code, use workspace tools instead of `shell`. "
            "Do not install dependencies yourself."
        )
        return "\n".join(lines)

    def _tool_error_message(
        self,
        *,
        tool_name: str,
        tool_call_id: str | None,
        message: str,
    ) -> ToolMessage:
        return ToolMessage(
            content=message,
            name=tool_name,
            tool_call_id=tool_call_id or "missing-tool-call-id",
            status="error",
        )

    def _is_blocked_shell_command(self, command: str) -> bool:
        return bool(BLOCKED_SHELL_PATTERN.search(command or ""))

    def _with_active_skill_section(self, request: ModelRequest) -> ModelRequest:
        active_skill_names = self._get_active_skill_names(request.state)
        active_skill_section = self._build_active_skill_section(active_skill_names)
        if not active_skill_section:
            return request

        if request.system_message is None:
            system_message = SystemMessage(content=active_skill_section.strip())
        else:
            system_message = SystemMessage(
                content=list(request.system_message.content_blocks)
                + [{"type": "text", "text": active_skill_section}]
            )
        return request.override(system_message=system_message)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._with_active_skill_section(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return await handler(self._with_active_skill_section(request))

    def _handle_tool_call(self, request):
        tool_name = request.tool_call.get("name")
        if not isinstance(tool_name, str):
            return None

        if tool_name in WORKSPACE_TOOL_NAMES:
            authorized_skills = self._get_authorized_skills(request.state, tool_name=tool_name)
            if not authorized_skills:
                return self._tool_error_message(
                    tool_name=tool_name,
                    tool_call_id=request.tool_call.get("id"),
                    message=(
                        f"Skill authorization error: `{tool_name}` requires an active skill "
                        "that explicitly lists it in `allowed-tools`. Load the right skill "
                        "with `load_skill` first."
                    ),
                )

        if tool_name == "shell":
            args = request.tool_call.get("args", {}) or {}
            command = args.get("command") if isinstance(args, dict) else None
            if isinstance(command, str) and self._is_blocked_shell_command(command):
                return self._tool_error_message(
                    tool_name=tool_name,
                    tool_call_id=request.tool_call.get("id"),
                    message=(
                        "Shell policy error: use workspace tools for Python or Node.js code "
                        "execution and rely on host-managed dependencies instead of "
                        "running installers from `shell`."
                    ),
                )

        return None

    def wrap_tool_call(self, request, handler):
        guarded_response = self._handle_tool_call(request)
        if guarded_response is not None:
            return guarded_response
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        guarded_response = self._handle_tool_call(request)
        if guarded_response is not None:
            return guarded_response
        return await handler(request)


class AgentConsoleLoggingMiddleware(AgentMiddleware):
    """Print model and tool activity to the console for debugging."""

    def __init__(self, *, agent_name: str) -> None:
        self.agent_name = agent_name

    def _log_model_response(self, response: ModelResponse) -> None:
        for message in response.result:
            if not isinstance(message, AIMessage):
                continue
            if _message_to_text(message).strip():
                print(f"======================{self.agent_name}:AIMessage==========================")
                print(f"AIMessage: {_message_to_text(message)}")
            if message.tool_calls:
                print(f"======================{self.agent_name}:AI_Tool_calls======================")
                print(f"Tool_calls: {message.tool_calls}")

    def _log_tool_output(self, response: Any, *, fallback_tool_name: str | None = None) -> None:
        tool_messages: list[ToolMessage] = []
        if isinstance(response, ToolMessage):
            tool_messages = [response]
        elif isinstance(response, Command):
            update = getattr(response, "update", None)
            if isinstance(update, dict):
                messages = update.get("messages", []) or []
                tool_messages = [
                    message for message in messages if isinstance(message, ToolMessage)
                ]

        for message in tool_messages:
            print(f"======================{self.agent_name}:ToolMessage========================")
            print(
                "ToolMessage: "
                f"{message.content}. "
                f"ToolName: {message.name or fallback_tool_name}"
            )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        response = handler(request)
        self._log_model_response(response)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        response = await handler(request)
        self._log_model_response(response)
        return response

    def wrap_tool_call(self, request, handler):
        response = handler(request)
        self._log_tool_output(response, fallback_tool_name=request.tool_call.get("name"))
        return response

    async def awrap_tool_call(self, request, handler):
        response = await handler(request)
        self._log_tool_output(response, fallback_tool_name=request.tool_call.get("name"))
        return response


class AgentRuntime:
    def __init__(
        self,
        checkpointer: AsyncPostgresSaver,
        rag_runtime: RagRuntime,
        skill_registry: SkillRegistry,
    ) -> None:
        self.skill_registry = skill_registry
        self.backend_root = get_backend_root()
        self.skill_toolset = SkillToolset(skill_registry)
        self.workspace_toolset = WorkspaceToolset()
        self.checkpointer = checkpointer
        self.rag_runtime = rag_runtime
        self.suggestion_generator = get_small_model(streaming=False)
        self._thread_locks: dict[str | None, asyncio.Lock] = {}
        self._thread_locks_guard = asyncio.Lock()

        if os.name == "nt":
            shell_command = ["cmd.exe", "/Q", "/K"]
        else:
            shell_command = ["/bin/bash"]

        base_middleware = [
            FilesystemFileSearchMiddleware(
                root_path=str(self.backend_root),
                use_ripgrep=True,
            ),
            # ShellToolMiddleware(
            #     workspace_root=str(self.backend_root / "workspace"),
            #     execution_policy=HostExecutionPolicy(),
            #     shell_command=shell_command,
            #     tool_description=(
            #         "Shell for system-command tasks only. "
            #         "Use cmd because you are working in Windows now. "
            #         "Use this tool only when a task explicitly requires OS or CLI execution. "
            #         "Do not use shell to run Python or Node.js code or to run the scripts of skills. "
            #         "Use workspace tools for temporary code and `run_skill_script` for scripts bundled with a skill."
            #     ),
            # ),
            SkillPromptMiddleware(skill_registry),
            SkillExecutionPolicyMiddleware(skill_registry),
            ToolRetryMiddleware(
                max_retries=3,
                backoff_factor=0.0,
                initial_delay=1.0,
            ),
        ]

        self.attachment_agent_runnable = create_agent(
            model=get_model(streaming=True),
            tools=self.skill_toolset.tools + self.workspace_toolset.tools,
            system_prompt=(
                "You analyze uploaded materials for user. "
                "Use the available skills when the task matches them. "
                "Prefer progressive disclosure: load the skill instructions first, then read bundled "
                "resources or run skill scripts when needed. If a loaded skill explicitly allows "
                "workspace tools, you may write temporary Python or JavaScript files to the agent workspace "
                "and execute them there. For document analysis, prefer `run_skill_script`. "
                "Never use `shell` to run Python, Node.js, npm, or pip commands."
            ),
            middleware=list(base_middleware),
            name="attachment_skill_agent",
        )

        self.ppt_agent_runnable = self._create_artifact_agent(
            base_middleware,
            agent_name="ppt_agent",
            system_prompt=(
                "You are a teaching PPT generation agent embedded inside a LangGraph workflow. "
                "Generate a real .pptx artifact. Use the `ppt-generator` skill. "
                "For new code, use workspace tools. For scripts that already belong to a skill, "
                "use `run_skill_script`. Do not use `shell` for Python or Node.js execution or installs."
            ),
        )
        self.docx_agent_runnable = self._create_artifact_agent(
            base_middleware,
            agent_name="docx_agent",
            system_prompt=(
                "You are a DOCX lesson-plan generation agent embedded inside a LangGraph workflow. "
                "Generate a real .docx lesson-plan artifact. Use the `docx` skill. "
                "Write any temporary code with workspace tools, and never install dependencies yourself."
            ),
        )
        self.html_game_agent_runnable = self._create_artifact_agent(
            base_middleware,
            agent_name="html_game_agent",
            system_prompt=(
                "You are an HTML interactive activity generation agent embedded inside a LangGraph workflow whose target user is teachers. "
                "Choose a topic and generate a single runnable .html artifact based on given information to help teacher teach in class. "
                "Use the `html-interactive` skill and avoid local build tooling or package installs."
            ),
        )

        self.streaming_graph = build_agent_graph(
            checkpointer=checkpointer,
            rag_runtime=rag_runtime,
            ppt_generate_node=self.ppt_generate_node,
            docx_generate_node=self.docx_generate_node,
            html_generate_node=self.html_game_generate_node,
        )
        self.graph = self.streaming_graph

    def _create_artifact_agent(
        self,
        base_middleware: list[Any],
        *,
        agent_name: str,
        system_prompt: str,
    ):
        middleware = [
            *base_middleware,
            AgentConsoleLoggingMiddleware(agent_name=agent_name),
        ]
        return create_agent(
            model=get_model(streaming=False),
            tools=self.skill_toolset.tools + self.workspace_toolset.tools,
            system_prompt=system_prompt,
            middleware=middleware,
            name=agent_name,
        )

    async def analyze_attachments(
        self,
        message: str,
        file_paths: list[str],
        *,
        thread_id: str | None = None,
        run_id: str | None = None,
        progress_reporter: ProgressReporter | None = None,
    ) -> str:
        if progress_reporter:
            progress_reporter.emit("attachment_analysis", "running")

        user_prompt = (
            "Analyze the uploaded attachment files according to the user's request. "
            "Load the proper skills based on the file types and follow them. "
            "Use bundled scripts or resources when needed, then return a concise useful summary.\n\n"
            f"User message: {message}\n"
            "Attachment file paths:\n"
            + "\n".join(f"- {Path(file_path)}" for file_path in file_paths)
        )
        final_msg_content = ""

        try:
            async for chunk in self.attachment_agent_runnable.astream(
                {"messages": [{"role": "user", "content": user_prompt}]},
                config=get_thread_config(
                    thread_id or run_id,
                    run_id=run_id,
                    progress_reporter=progress_reporter,
                ),
                stream_mode="updates",
                version="v2",
            ):
                if chunk["type"] != "updates":
                    continue

                for step, data in chunk["data"].items():
                    if step == "tools":
                        print("======================ToolMessage========================")
                        print(
                            "ToolMessage: "
                            f"{data['messages'][-1].content}. "
                            f"ToolName: {data['messages'][-1].name}"
                        )
                    if step == "model":
                        if data["messages"][-1].content:
                            print("======================AIMessage==========================")
                            print(f"AIMessage: {data['messages'][-1].content}")
                        if data["messages"][-1].tool_calls:
                            print("======================AI_Tool_calls======================")
                            print(f"Tool_calls: {data['messages'][-1].tool_calls}")
                        final_msg_content = data["messages"][-1].content
        except Exception as exc:
            if progress_reporter:
                progress_reporter.emit("attachment_analysis", "failed", detail=str(exc))
            raise

        if progress_reporter:
            progress_reporter.emit("attachment_analysis", "success", detail="已完成附件分析")
        return final_msg_content

    async def _get_thread_lock(self, thread_id: str | None) -> asyncio.Lock:
        async with self._thread_locks_guard:
            lock = self._thread_locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._thread_locks[thread_id] = lock
            return lock

    async def _should_resume_thread(self, thread_id: str | None) -> bool:
        if not thread_id:
            return False
        state_snapshot = await self.streaming_graph.aget_state(get_thread_config(thread_id))
        interrupts = getattr(state_snapshot, "interrupts", ()) or ()
        next_nodes = tuple(getattr(state_snapshot, "next", ()) or ())
        return bool(interrupts) and INTERRUPT_FOR_USERINPUT_NODE in next_nodes

    async def _get_graph_input_with_plan(
        self,
        message: str,
        thread_id: str | None,
        *,
        plan_id: int | None,
        attachment_text: str | None = None,
        attachment_paths: list[str] | None = None,
    ):
        if await self._should_resume_thread(thread_id):
            if attachment_text:
                return Command(
                    resume={
                        "message": message,
                        "attachment_text": attachment_text,
                        "attachment_paths": attachment_paths,
                    }
                )
            return Command(resume=message)

        graph_input: dict[str, Any] = {
            "messages": build_input_messages(message, attachment_text, attachment_paths),
            "ppt_result": _default_subagent_result("ppt"),
            "lesson_plan_result": _default_subagent_result("docx"),
            "game_result": _default_subagent_result("html-game"),
        }
        if plan_id is not None:
            graph_input["plan_id"] = plan_id
        return graph_input

    def _should_emit_text_chunk(
        self,
        metadata: dict[str, Any],
        namespace: tuple[str, ...],
    ) -> bool:
        langgraph_node = metadata.get("langgraph_node")
        _ = namespace
        return langgraph_node in ROOT_STREAMING_NODES

    async def _get_visible_thread_messages(self, thread_id: str) -> list[AnyMessage]:
        state_snapshot = await self.streaming_graph.aget_state(get_thread_config(thread_id))
        values = getattr(state_snapshot, "values", {}) or {}
        messages = values.get("messages", []) or []
        return [message for message in messages if isinstance(message, BaseMessage)]

    async def _generate_follow_up_suggestions(self, thread_id: str) -> list[str]:
        messages = await self._get_visible_thread_messages(thread_id)
        final_response_text = get_final_response_text(messages)
        if not final_response_text:
            return []

        conversation_lines = _build_suggestion_conversation(messages)
        if not conversation_lines:
            return []

        prompt_messages = [
            SystemMessage(
                content=(
                    "我将提供一段 AI 与用户的对话。"
                    "请扮演用户，生成恰好 3 条最自然、最有价值的简短的中文回复。"
                    "请严格使用换行分隔每一条建议，每行只写一条。"
                    "每条都必须是用户可以直接发送给 AI 的完整句子。"
                    "建议要简洁、清晰、和刚刚的 AI 回复紧密相关。"
                    "不要编号，不要解释，只返回 3 行纯文本。"
                )
            ),
            HumanMessage(
                content=(
                    "请根据下面的对话生成 3 条继续追问：\n\n"
                    + "\n".join(conversation_lines)
                )
            ),
        ]

        try:
            result = await self.suggestion_generator.ainvoke(prompt_messages)
        except Exception as exc:
            print(f"[suggestions] generation failed: {exc}")
            return []

        suggestions = _sanitize_suggestions(
            _split_suggestion_lines(_message_to_text(result).strip())
        )
        if len(suggestions) < SUGGESTION_COUNT:
            print("[suggestions] discarded because the model did not return enough unique suggestions.")
            return []
        return suggestions

    def _artifact_agent_thread_id(self, thread_id: str, artifact_type: ArtifactType) -> str:
        return f"{thread_id}--artifact-{artifact_type}"

    def _artifact_run_id(self, run_id: str, artifact_type: ArtifactType) -> str:
        return f"{run_id}-{artifact_type}"

    def _build_artifact_prompt(self, state: TeachingAssistantState, artifact_type: ArtifactType) -> str:
        latest_user_messages = [
            _message_to_text(message).strip()
            for message in state.get("messages", [])
            if isinstance(message, HumanMessage)
        ]
        latest_request = latest_user_messages[-1] if latest_user_messages else ""
        teaching_design_plan = state.get("teaching_design_plan", "")
        teaching_metadata = state.get("teaching_metadata")
        rag_context = state.get("rag_context", "")

        artifact_instruction = {
            "ppt": (
                "Generate a real `.pptx` teaching deck. "
                "You must load and follow the `ppt-generator` skill, then write the final file to `AGENT_OUTPUT_DIR`."
            ),
            "docx": (
                "Generate a real `.docx` lesson-plan document. "
                "You must load and follow the `docx` skill, then write the final file to `AGENT_OUTPUT_DIR`."
            ),
            "html-game": (
                "Generate a single runnable `.html` interactive activity or experiment page. "
                "You must load and follow the `html-interactive` skill, then write the final file to your workspace."
            ),
        }[artifact_type]

        return (
            f"{artifact_instruction}\n\n"
            f"Latest user request:\n{latest_request}\n\n"
            f"Teaching metadata:\n{teaching_metadata}\n\n"
            f"Teaching design plan:\n{teaching_design_plan}\n\n"
            f"Retrieved context:\n{rag_context}\n\n"
            "If required dependencies are missing, explain the missing dependency clearly. "
            "Do not use shell to install anything."
        )

    def _extract_best_error(self, invoke_result: dict[str, Any] | None, exc: Exception | None = None) -> str:
        if exc is not None:
            return str(exc)
        if invoke_result:
            messages = invoke_result.get("messages", []) or []
            final_text = get_final_response_text(messages)
            if final_text:
                return final_text
        return "No artifact file was produced."

    def _snapshot_generated_outputs(
        self,
        config: RunnableConfig,
        artifact_type: ArtifactType,
    ) -> dict[str, float]:
        paths = get_workspace_paths(config)
        allowed_extensions = ARTIFACT_ALLOWED_EXTENSIONS[artifact_type]
        snapshots: dict[str, float] = {}
        for root in (paths.output_root, paths.workspace_root):
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in allowed_extensions:
                    snapshots[str(path)] = path.stat().st_mtime
        return snapshots

    def _artifact_candidate_priority(self, paths: Any, path: Path) -> tuple[int, float]:
        try:
            path.relative_to(paths.output_root)
            return (3, path.stat().st_mtime)
        except ValueError:
            pass

        try:
            relative_path = path.relative_to(paths.workspace_root)
        except ValueError:
            return (0, path.stat().st_mtime)

        top_level_dir = relative_path.parts[0].lower() if relative_path.parts else ""
        if top_level_dir in {"output", "outputs", "dist", "build"}:
            return (2, path.stat().st_mtime)
        return (1, path.stat().st_mtime)

    def _find_generated_output(
        self,
        config: RunnableConfig,
        artifact_type: ArtifactType,
        *,
        before_snapshot: dict[str, float] | None = None,
    ) -> Path | None:
        paths = get_workspace_paths(config)
        after_snapshot = self._snapshot_generated_outputs(config, artifact_type)
        candidates = [
            Path(raw_path)
            for raw_path, mtime in after_snapshot.items()
            if before_snapshot is None or before_snapshot.get(raw_path) != mtime
        ]

        if not candidates:
            candidates = [
                Path(raw_path)
                for raw_path in after_snapshot
                if Path(raw_path).is_relative_to(paths.output_root)
            ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: self._artifact_candidate_priority(paths, item),
        )

    def _build_missing_output_error(
        self,
        invoke_result: dict[str, Any] | None,
        *,
        artifact_type: ArtifactType,
        config: RunnableConfig,
    ) -> str:
        paths = get_workspace_paths(config)
        final_text = self._extract_best_error(invoke_result)
        extension_hint = ", ".join(ARTIFACT_ALLOWED_EXTENSIONS[artifact_type])
        return (
            f"No generated artifact file was detected for {artifact_type}. "
            f"Expected a newly created or updated {extension_hint} file, preferably under "
            f"AGENT_OUTPUT_DIR ({paths.output_root}). Final agent message: {final_text}"
        )

    async def _run_artifact_generation(
        self,
        *,
        state: TeachingAssistantState,
        config: RunnableConfig | None,
        artifact_type: ArtifactType,
        agent_runnable: Any,
    ) -> dict[str, Any]:
        step_key = ARTIFACT_STEP_KEYS[artifact_type]
        state_key = ARTIFACT_STATE_KEYS[artifact_type]
        main_reporter = _get_configurable_value(config, "progress_reporter")
        if isinstance(main_reporter, ProgressReporter):
            main_reporter.emit(step_key, "running", detail=f"{_artifact_display_name(artifact_type)}生成中")

        thread_id = str(_get_configurable_value(config, "thread_id") or "").strip()
        run_id = str(_get_configurable_value(config, "run_id") or "").strip()
        plan_id = state.get("plan_id")
        artifact_title = _artifact_display_name(artifact_type)
        emitter = _get_artifact_event_emitter(config)

        if not thread_id or not run_id or plan_id is None:
            error_message = "Missing thread_id, run_id, or plan_id for artifact generation."
            if isinstance(main_reporter, ProgressReporter):
                main_reporter.emit(step_key, "failed", detail=error_message)
            return {state_key: _failed_subagent_result(artifact_type, error=error_message)}

        sub_run_id = self._artifact_run_id(run_id, artifact_type)
        artifact_record = None

        try:
            async with AsyncSessionLocal() as db:
                artifact_record = await artifact_service.create_running_artifact(
                    db,
                    plan_id=plan_id,
                    thread_id=thread_id,
                    artifact_type=artifact_type,
                    run_id=sub_run_id,
                    title=artifact_title,
                )
                if emitter:
                    emitter(
                        {
                            "event": "artifact",
                            "data": {
                                "run_id": run_id,
                                "artifact": _artifact_payload(artifact_record),
                            },
                        }
                    )

            agent_config = get_thread_config(
                self._artifact_agent_thread_id(thread_id, artifact_type),
                run_id=sub_run_id,
            )
            output_snapshot_before = self._snapshot_generated_outputs(
                agent_config,
                artifact_type,
            )
            invoke_result = await agent_runnable.ainvoke(
                {"messages": [{"role": "user", "content": self._build_artifact_prompt(state, artifact_type)}]},
                config=agent_config,
            )
            output_path = self._find_generated_output(
                agent_config,
                artifact_type,
                before_snapshot=output_snapshot_before,
            )

            if output_path is None:
                raise RuntimeError(
                    self._build_missing_output_error(
                        invoke_result,
                        artifact_type=artifact_type,
                        config=agent_config,
                    )
                )

            async with AsyncSessionLocal() as db:
                refreshed_record = await artifact_service.require_artifact_by_id(db, artifact_record.id)
                refreshed_record = await artifact_service.mark_artifact_ready(
                    db,
                    refreshed_record,
                    output_path=output_path,
                    title=artifact_title,
                )
                if emitter:
                    emitter(
                        {
                            "event": "artifact",
                            "data": {
                                "run_id": run_id,
                                "artifact": _artifact_payload(refreshed_record),
                            },
                        }
                    )

            if isinstance(main_reporter, ProgressReporter):
                main_reporter.emit(step_key, "success", detail=f"{artifact_title}已生成")
            return {
                state_key: _success_subagent_result(
                    artifact_type,
                    artifact_id=artifact_record.id,
                    title=artifact_title,
                )
            }
        except Exception as exc:
            error_message = str(exc)
            if artifact_record is not None:
                async with AsyncSessionLocal() as db:
                    refreshed_record = await artifact_service.require_artifact_by_id(db, artifact_record.id)
                    refreshed_record = await artifact_service.mark_artifact_failed(
                        db,
                        refreshed_record,
                        error_message=error_message,
                    )
                    if emitter:
                        emitter(
                            {
                                "event": "artifact",
                                "data": {
                                    "run_id": run_id,
                                    "artifact": _artifact_payload(refreshed_record),
                                },
                            }
                        )
                    artifact_record = refreshed_record

            if isinstance(main_reporter, ProgressReporter):
                main_reporter.emit(step_key, "failed", detail=error_message)
            return {
                state_key: _failed_subagent_result(
                    artifact_type,
                    artifact_id=getattr(artifact_record, "id", None),
                    title=artifact_title,
                    error=error_message,
                )
            }

    async def ppt_generate_node(
        self,
        state: TeachingAssistantState,
        config: Optional[RunnableConfig] = None,
    ) -> dict[str, Any]:
        return await self._run_artifact_generation(
            state=state,
            config=config,
            artifact_type="ppt",
            agent_runnable=self.ppt_agent_runnable,
        )

    async def docx_generate_node(
        self,
        state: TeachingAssistantState,
        config: Optional[RunnableConfig] = None,
    ) -> dict[str, Any]:
        return await self._run_artifact_generation(
            state=state,
            config=config,
            artifact_type="docx",
            agent_runnable=self.docx_agent_runnable,
        )

    async def html_game_generate_node(
        self,
        state: TeachingAssistantState,
        config: Optional[RunnableConfig] = None,
    ) -> dict[str, Any]:
        return await self._run_artifact_generation(
            state=state,
            config=config,
            artifact_type="html-game",
            agent_runnable=self.html_game_agent_runnable,
        )

    async def stream_agent_events(
        self,
        message: str,
        thread_id: str | None,
        *,
        run_id: str,
        plan_id: int | None = None,
        attachment_paths: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        graph_thread_id = thread_id or run_id
        lock = await self._get_thread_lock(graph_thread_id)
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit_progress_event(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        def emit_artifact_event(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        progress_tracker = ProgressTracker(run_id=run_id)
        progress_reporter = ProgressReporter(
            progress_tracker,
            emit_event=emit_progress_event,
        )
        register_progress_reporter(run_id, progress_reporter)

        async def produce_events() -> None:
            try:
                async with lock:
                    attachment_text: str | None = None
                    if attachment_paths:
                        attachment_text = await self.analyze_attachments(
                            message,
                            attachment_paths,
                            thread_id=graph_thread_id,
                            run_id=run_id,
                            progress_reporter=progress_reporter,
                        )

                    graph_input = await self._get_graph_input_with_plan(
                        message,
                        graph_thread_id,
                        plan_id=plan_id,
                        attachment_text=attachment_text,
                        attachment_paths=attachment_paths,
                    )
                    received_text_chunk = False
                    async for event in self.streaming_graph.astream(
                        graph_input,
                        config=get_thread_config(
                            graph_thread_id,
                            run_id=run_id,
                            progress_reporter=progress_reporter,
                            artifact_event_emitter=emit_artifact_event,
                        ),
                        stream_mode="messages",
                        subgraphs=True,
                        version="v2",
                    ):
                        if event.get("type") != "messages":
                            continue

                        chunk, metadata = event["data"]
                        if not isinstance(chunk, (AIMessageChunk, AIMessage)):
                            continue
                        if not isinstance(metadata, dict):
                            continue

                        namespace = tuple(event.get("ns", ()) or ())
                        if not self._should_emit_text_chunk(metadata, namespace):
                            continue

                        text = _message_to_text(chunk)
                        if text:
                            received_text_chunk = True
                            await event_queue.put(
                                {
                                    "event": "token",
                                    "data": {
                                        "run_id": run_id,
                                        "text": text,
                                    },
                                }
                            )

                    if not received_text_chunk:
                        print(
                            "[stream_agent_events] completed without any text chunks. "
                            "This usually means nested model calls did not propagate streaming callbacks."
                        )
                    elif graph_thread_id:
                        suggestions = await self._generate_follow_up_suggestions(graph_thread_id)
                        if suggestions:
                            await event_queue.put(
                                {
                                    "event": "suggestions",
                                    "data": {
                                        "run_id": run_id,
                                        "suggestions": suggestions,
                                    },
                                }
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await event_queue.put(
                    {
                        "event": "error",
                        "data": {
                            "run_id": run_id,
                            "message": str(exc),
                        },
                    }
                )
            finally:
                await event_queue.put({"event": "__end__", "data": None})

        producer = asyncio.create_task(produce_events())

        try:
            while True:
                item = await event_queue.get()
                if item["event"] == "__end__":
                    break
                yield item
        finally:
            unregister_progress_reporter(run_id)
            if not producer.done():
                producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer

    async def close(self) -> None:
        self._thread_locks.clear()
        await close_agent_checkpointer()


async def create_agent_runtime(
    rag_runtime: RagRuntime,
    skill_registry: SkillRegistry | None = None,
) -> AgentRuntime:
    checkpointer = await init_agent_checkpointer()
    return AgentRuntime(
        checkpointer=checkpointer,
        rag_runtime=rag_runtime,
        skill_registry=skill_registry or create_skill_registry(),
    )


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise RuntimeError("Agent runtime is not initialized.")
    return runtime
