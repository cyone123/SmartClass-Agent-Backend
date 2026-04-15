from __future__ import annotations

from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage

from app.core.agent import (
    AgentRuntime,
    SkillExecutionPolicyMiddleware,
    SkillPromptMiddleware,
    get_thread_config,
)
from app.core.progress import ProgressReporter, ProgressTracker
from app.core.skills import SkillRegistry, SkillToolset
from app.core.workspace import WorkspaceToolset, get_workspace_paths


class ToolCallingFakeChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def _write_skill(
    skills_root: Path,
    *,
    name: str,
    description: str,
    allowed_tools: list[str] | None = None,
) -> None:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    allowed_tools_block = ""
    if allowed_tools:
        allowed_tools_block = "allowed-tools:\n" + "".join(
            f"  - {tool_name}\n" for tool_name in allowed_tools
        )
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"{allowed_tools_block}"
            "---\n"
            "\n"
            f"# {name}\n"
            "Follow the skill instructions.\n"
        ),
        encoding="utf-8",
    )


def _build_agent(registry: SkillRegistry, responses: list[AIMessage]):
    return create_agent(
        model=ToolCallingFakeChatModel(responses=responses),
        tools=SkillToolset(registry).tools + WorkspaceToolset().tools,
        middleware=[
            SkillPromptMiddleware(registry),
            SkillExecutionPolicyMiddleware(registry),
        ],
        system_prompt="Test agent.",
    )


def test_agent_can_load_skill_write_and_run_workspace_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root,
        name="coder",
        description="Generate temporary Python code.",
        allowed_tools=["write_workspace_file", "run_workspace_code", "read_workspace_file"],
    )
    registry = SkillRegistry.from_root(skills_root)
    events: list[dict] = []
    reporter = ProgressReporter(
        ProgressTracker(run_id="run-1"),
        emit_event=events.append,
    )
    agent = _build_agent(
        registry,
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "load_skill",
                        "args": {"skill_name": "coder"},
                        "id": "tool-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_workspace_file",
                        "args": {
                            "relative_path": "hello.py",
                            "content": "from pathlib import Path\nimport os\n"
                            "output_dir = Path(os.environ['AGENT_OUTPUT_DIR'])\n"
                            "output_dir.mkdir(parents=True, exist_ok=True)\n"
                            "(output_dir / 'hello.txt').write_text('hello from workspace', encoding='utf-8')\n"
                            "print('script-finished')\n",
                            "overwrite": True,
                        },
                        "id": "tool-2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_workspace_code",
                        "args": {"language": "python", "entrypoint": "hello.py"},
                        "id": "tool-3",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="done"),
        ],
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Create a tiny script."}]},
        config=get_thread_config(
            "thread-1",
            run_id="run-1",
            progress_reporter=reporter,
        ),
    )

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert any(message.name == "load_skill" for message in tool_messages)
    assert any(message.name == "write_workspace_file" for message in tool_messages)
    run_message = next(message for message in tool_messages if message.name == "run_workspace_code")
    assert "hello.txt" in str(run_message.content)
    assert result["active_skills"] == ["coder"]

    paths = get_workspace_paths(get_thread_config("thread-1", run_id="run-1"))
    output_file = paths.output_root / "hello.txt"
    assert output_file.read_text(encoding="utf-8") == "hello from workspace"

    progress_steps = [
        step["step_key"]
        for event in events
        if event["event"] == "progress"
        for step in event["data"]["steps"]
    ]
    assert "skill_activation" in progress_steps
    assert "code_preparation" in progress_steps
    assert "code_execution" in progress_steps


@pytest.mark.parametrize(
    ("skill_allowed_tools", "responses"),
    [
        (
            None,
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_workspace_file",
                            "args": {
                                "relative_path": "blocked.py",
                                "content": "print('blocked')",
                                "overwrite": True,
                            },
                            "id": "tool-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="done"),
            ],
        ),
        (
            [],
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "load_skill",
                            "args": {"skill_name": "reader"},
                            "id": "tool-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_workspace_file",
                            "args": {
                                "relative_path": "blocked.py",
                                "content": "print('blocked')",
                                "overwrite": True,
                            },
                            "id": "tool-2",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="done"),
            ],
        ),
    ],
)
def test_agent_blocks_workspace_tools_without_authorized_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skill_allowed_tools: list[str] | None,
    responses: list[AIMessage],
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root,
        name="reader",
        description="Reads only.",
        allowed_tools=skill_allowed_tools,
    )
    registry = SkillRegistry.from_root(skills_root)
    agent = _build_agent(registry, responses)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Try writing code."}]},
        config=get_thread_config("thread-1", run_id="run-1"),
    )

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    error_messages = [message for message in tool_messages if message.name == "write_workspace_file"]
    assert error_messages
    assert "Skill authorization error" in str(error_messages[-1].content)

    paths = get_workspace_paths(get_thread_config("thread-1", run_id="run-1"))
    assert not (paths.workspace_root / "blocked.py").exists()


def test_find_generated_output_accepts_workspace_output_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    runtime = AgentRuntime.__new__(AgentRuntime)
    config = get_thread_config("thread-1--artifact-html", run_id="run-1-html")
    paths = get_workspace_paths(config)

    before_snapshot = runtime._snapshot_generated_outputs(config, "html-game")

    fallback_output = paths.workspace_root / "output" / "newton_first_law.html"
    fallback_output.parent.mkdir(parents=True, exist_ok=True)
    fallback_output.write_text("<html><body>ready</body></html>", encoding="utf-8")

    detected = runtime._find_generated_output(
        config,
        "html-game",
        before_snapshot=before_snapshot,
    )

    assert detected == fallback_output


def test_missing_output_error_mentions_expected_output_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    runtime = AgentRuntime.__new__(AgentRuntime)
    config = get_thread_config("thread-1--artifact-html", run_id="run-1-html")
    invoke_result = {"messages": [AIMessage(content="HTML game generated successfully.")]}

    error_message = runtime._build_missing_output_error(
        invoke_result,
        artifact_type="html-game",
        config=config,
    )

    assert "No generated artifact file was detected for html-game." in error_message
    assert "AGENT_OUTPUT_DIR" in error_message
    assert "HTML game generated successfully." in error_message
