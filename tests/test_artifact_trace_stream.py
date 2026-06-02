from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage

from app.api.chat import router as chat_router
from app.core.agent import AgentRuntime, get_agent_runtime, get_thread_config
from app.core.auth import get_current_user
from app.dependencies.db import get_db


class FakeArtifactRunnable:
    async def astream(self, inputs, *, config=None, stream_mode=None, version=None):
        _ = inputs, config, stream_mode, version
        yield {
            "type": "updates",
            "data": {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "read_workspace_file",
                                    "args": {"relative_path": "source_artifact.html"},
                                    "id": "tool-1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    ]
                }
            },
        }
        yield {
            "type": "updates",
            "data": {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content="Loaded source artifact content.",
                            tool_call_id="tool-1",
                            name="read_workspace_file",
                        )
                    ]
                }
            },
        }
        yield {
            "type": "updates",
            "data": {
                "model": {
                    "messages": [
                        AIMessage(content="Updated the deck and wrote the final file to AGENT_OUTPUT_DIR.")
                    ]
                }
            },
        }


def test_stream_artifact_agent_updates_emits_trace_entries() -> None:
    runtime = AgentRuntime.__new__(AgentRuntime)
    events: list[dict] = []

    def emit_trace(kind, title, *, content=None, status=None) -> None:
        events.append(
            {
                "kind": kind,
                "title": title,
                "content": content,
                "status": status,
            }
        )

    async def run() -> None:
        result = await runtime._stream_artifact_agent_updates(
            FakeArtifactRunnable(),
            prompt="Generate a PPT artifact.",
            agent_config=get_thread_config("thread-1--artifact-ppt", run_id="run-1-ppt"),
            emit_trace_entry=emit_trace,
        )

        assert result is not None
        assert result["messages"][0].content == "Updated the deck and wrote the final file to AGENT_OUTPUT_DIR."
        assert [event["kind"] for event in events] == ["tool_call", "tool_result", "ai_message"]
        assert events[0]["title"] == "调用工具 · read_workspace_file"
        assert "source_artifact.html" in (events[0]["content"] or "")
        assert events[1]["title"] == "工具结果 · read_workspace_file"
        assert "Loaded source artifact content." in (events[1]["content"] or "")

    asyncio.run(run())


def test_chat_stream_forwards_artifact_trace_events() -> None:
    class FakeAgentRuntime:
        async def stream_agent_events(self, *args, **kwargs):
            _ = args, kwargs
            yield {
                "event": "artifact_trace",
                "data": {
                    "run_id": "run-1",
                    "artifact_run_id": "run-1-ppt",
                    "artifact_type": "ppt",
                    "artifact_title": "课件 PPT",
                    "mode": "create",
                    "entry": {
                        "entry_id": "run-1-ppt-trace-1",
                        "kind": "status",
                        "title": "开始生成课件 PPT",
                        "status": "running",
                    },
                },
            }

    async def run() -> None:
        app = FastAPI()
        app.include_router(chat_router)

        async def override_db():
            yield None

        async def override_agent_runtime():
            return FakeAgentRuntime()

        async def override_current_user():
            return type("User", (), {"id": 1})()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_agent_runtime] = override_agent_runtime
        app.dependency_overrides[get_current_user] = override_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/chat/stream",
                json={"message": "请生成课件"},
            )

        assert response.status_code == 200
        assert "event: artifact_trace" in response.text
        assert "\"artifact_run_id\": \"run-1-ppt\"" in response.text

    asyncio.run(run())
