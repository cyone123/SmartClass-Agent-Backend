from __future__ import annotations

import os
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Callable

from fastapi import Request
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.core.graph import build_agent_graph, build_input_messages
from app.core.rag import RagRuntime
from app.core.skills import SkillRegistry, create_skill_registry, SkillToolset
from app.config import get_backend_root
from app.dependencies.db import close_agent_checkpointer, init_agent_checkpointer
from langchain.agents import create_agent
from langchain.agents.middleware import (
    FilesystemFileSearchMiddleware,
    ToolRetryMiddleware,
    ShellToolMiddleware,
    HostExecutionPolicy,
)
from langchain.agents.middleware import ModelRequest, ModelResponse, AgentMiddleware
from langchain.messages import SystemMessage
from app.core.llm import get_model

INTERRUPT_FOR_USERINPUT_NODE = "interrupt_for_userinput"
PPT_AGENT_NAME = "ppt_generate_agent"
PPT_AGENT_NODE = "ppt_generate_agent_node"
ROOT_STREAMING_NODES = {"normal_chat_node", "follow_up_questioner", "teaching_design_planner"}


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


class SkillPromptMiddleware(AgentMiddleware):
    """Inject skill metadata into the agent system prompt."""

    def __init__(self, registry: SkillRegistry) -> None:
        skill_lines = [
            f"- **{skill.name}**: {skill.description}"
            for skill in registry.list_metadata()
        ]
        self.skills_prompt = "\n".join(skill_lines)

    def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        skills_addendum = (
            f"\n\n## Available Skills\n\n{self.skills_prompt}\n\n"
            "Only the metadata above is preloaded. When a request matches a skill, "
            "use `load_skill` to read its instructions. Then use `read_skill_resource` "
            "or `run_skill_script` only when the loaded skill tells you to. When "
            "calling `run_skill_script`, pass `script_args` as a string array."
        )

        if request.system_message is None:
            new_system_message = SystemMessage(content=skills_addendum.strip())
        else:
            new_content = list(request.system_message.content_blocks) + [
                {"type": "text", "text": skills_addendum}
            ]
            new_system_message = SystemMessage(content=new_content)
        modified_request = request.override(system_message=new_system_message)
        return handler(modified_request)


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
        if os.name == "nt":
            shell_command = ["cmd.exe", "/Q", "/K"]
        else:
            shell_command = ["/bin/bash"]
        middleware = [
            FilesystemFileSearchMiddleware(
                root_path=str(self.backend_root),
                use_ripgrep=True,
            ),
            ShellToolMiddleware(
                workspace_root=str(self.backend_root),
                execution_policy=HostExecutionPolicy(),
                shell_command=shell_command,
                tool_description=(
                    "Shell for system-command tasks only. "
                    "Use cmd because you are working in windows now. "
                    "Use this tool only when a task explicitly requires OS/CLI execution, "
                    "such as npm, ffmpeg, process diagnostics, or filesystem commands "
                    "that cannot be completed through dedicated tools. "
                ),
            ),
            SkillPromptMiddleware(skill_registry),
            ToolRetryMiddleware(
                max_retries=3,
                backoff_factor=0.0,
                initial_delay=1.0,
            ),
        ]
        self.attachment_agent_runnable = create_agent(
            model=get_model(streaming=True),
            tools=self.skill_toolset.tools,
            system_prompt=(
                "You are an agent that analyze uploaded "
                "materials or generate courseware. Use the available skills when the task "
                "matches their descriptions. Prefer progressive disclosure: load the "
                "skill instructions first, then read bundled resources or run skill scripts when needed. "
                # "Do NOT use shell for docx/pdf/xlsx analysis. "
                "For document analysis, use 'run_skill_script' instead. "
            ),
            middleware=middleware,
            name="attachment_skill_agent",
        )
        self.ppt_agent_runnable = create_agent(
            model=get_model(streaming=False),
            tools=self.skill_toolset.tools,
            system_prompt=(
                "You are a ppt generate agent embedded inside a LangGraph workflow. "
                "Use the teaching design plan already present and user's messages in the conversation as your primary source of truth. "
                "Use skills and tools to generate a ppt according to user' request. "
            ),
            middleware=middleware,
            name=PPT_AGENT_NAME,
        )

        self.checkpointer = checkpointer
        self.rag_runtime = rag_runtime
        self.graph = build_agent_graph(
            checkpointer=checkpointer,
            rag_runtime=rag_runtime,
            agent_runnable=self.ppt_agent_runnable,
        )

        self.streaming_graph = build_agent_graph(
            streaming=True,
            checkpointer=checkpointer,
            rag_runtime=rag_runtime,
            agent_runnable=self.ppt_agent_runnable,
        )
        self._thread_locks: dict[str, asyncio.Lock] = {}
        self._thread_locks_guard = asyncio.Lock()

    async def analyze_attachments(self, message, file_paths: list[str]) -> str:
        print("============正在分析附件信息=========")
        user_prompt = (
            "Analyze the uploaded attachment files accroding to user's request. "
            f"Load the proper skills based on the file and follow it. "
            "Use bundled scripts or resources when needed, then return a concise but "
            "useful summary without any unnecessary content.\n\n"
            f"user's message: {message}"
            "Attachment file paths:\n"
            + "\n".join(f"- {Path(file_path)}" for file_path in file_paths)
        )
        final_msg_content = ""
        async for chunk in self.attachment_agent_runnable.astream(
            {
                "messages": [{"role": "user", "content": user_prompt}]
            },
            stream_mode="updates",
            version="v2",
        ):
            if chunk["type"] == "updates":
                for step, data in chunk["data"].items():
                    if step == "tools":
                        print("======================ToolMessage========================")
                        print(f"ToolMessage: {data['messages'][-1].content}. ToolName: {data['messages'][-1].name}")
                    if step == "model":
                        if data["messages"][-1].content:
                            print("======================AIMessage==========================")
                            print(f"AIMessage: {data['messages'][-1].content}")
                        if data["messages"][-1].tool_calls:
                            print("======================AI_Tool_calls======================")
                            print(f"Tool_calls: {data['messages'][-1].tool_calls}")
                        final_msg_content = data["messages"][-1].content
        return final_msg_content

    async def _get_thread_lock(self, thread_id: str) -> asyncio.Lock:
        async with self._thread_locks_guard:
            lock = self._thread_locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._thread_locks[thread_id] = lock
            return lock

    async def _should_resume_thread(self, thread_id: str) -> bool:
        state_snapshot = await self.streaming_graph.aget_state(get_thread_config(thread_id))
        interrupts = getattr(state_snapshot, "interrupts", ()) or ()
        next_nodes = tuple(getattr(state_snapshot, "next", ()) or ())
        return bool(interrupts) and INTERRUPT_FOR_USERINPUT_NODE in next_nodes

    async def _get_graph_input(self, message: str, thread_id: str):
        return await self._get_graph_input_with_plan(message, thread_id, plan_id=None)

    async def _get_graph_input_with_plan(
        self,
        message: str,
        thread_id: str,
        *,
        plan_id: int | None,
        attachment_text: str | None = None,
        attachment_paths: list[str] | None = None
    ):
        if await self._should_resume_thread(thread_id):
            if attachment_text:
                return Command(
                    resume={
                        "message": message,
                        "attachment_text": attachment_text,
                        "attachment_paths": attachment_paths
                    }
                )
            return Command(resume=message)

        graph_input = {
            "messages": build_input_messages(message, attachment_text, attachment_paths),
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
        lc_agent_name = metadata.get("lc_agent_name")
        return (
            langgraph_node in ROOT_STREAMING_NODES
            # or any(part.startswith(f"{GRAPH_AGENT_NODE}:") for part in namespace)
            # or lc_agent_name == GRAPH_AGENT_NAME
        )

    async def stream_agent_response(
        self,
        message: str,
        thread_id: str,
        *,
        plan_id: int | None = None,
        attachment_text: str | None = None,
        attachment_paths: list[str] | None = None
    ) -> AsyncIterator[str]:
        lock = await self._get_thread_lock(thread_id)
        async with lock:
            graph_input = await self._get_graph_input_with_plan(
                message,
                thread_id,
                plan_id=plan_id,
                attachment_text=attachment_text,
                attachment_paths=attachment_paths
            )
            received_text_chunk = False
            async for event in self.streaming_graph.astream(
                graph_input,
                config=get_thread_config(thread_id),
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
                    yield text

            if not received_text_chunk:
                print(
                    "[stream_agent_response] completed without any text chunks. "
                    "This usually means nested model calls did not propagate streaming "
                    "callbacks, or the upstream model endpoint did not return stream tokens."
                )

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
