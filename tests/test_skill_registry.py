from __future__ import annotations

from pathlib import Path

from langchain.tools import ToolRuntime

from app.core.skills import SkillRegistry, SkillToolset


def _write_skill(skill_root: Path, *, body: str) -> None:
    skill_root.mkdir(parents=True, exist_ok=True)
    (skill_root / "SKILL.md").write_text(body, encoding="utf-8")


def _tool_runtime() -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=None,
        config={"configurable": {"thread_id": "thread-1", "run_id": "run-1"}},
        stream_writer=lambda payload: None,
        tool_call_id=None,
        store=None,
    )


def test_skill_registry_parses_extended_frontmatter(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills" / "coder"
    _write_skill(
        skill_root,
        body=(
            "---\n"
            "name: coder\n"
            "description: Generate and execute temporary code.\n"
            "compatibility: Requires Python or Node.js on host.\n"
            "allowed-tools:\n"
            "  - write_workspace_file\n"
            "  - run_workspace_code\n"
            "metadata:\n"
            '  author: test\n'
            '  version: "1.0"\n'
            "unknown-field: ignored\n"
            "---\n"
            "\n"
            "# Test Skill\n"
        ),
    )

    registry = SkillRegistry.from_root(tmp_path / "skills")
    skill = registry.get_skill("coder")

    assert skill.compatibility == "Requires Python or Node.js on host."
    assert skill.allowed_tools == ("write_workspace_file", "run_workspace_code")
    assert skill.metadata_map == {"author": "test", "version": "1.0"}


def test_load_skill_returns_compatibility_and_allowed_tools(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills" / "coder"
    _write_skill(
        skill_root,
        body=(
            "---\n"
            "name: coder\n"
            "description: Generate and execute temporary code.\n"
            "compatibility: Requires Python.\n"
            "allowed-tools: write_workspace_file, run_workspace_code\n"
            "---\n"
            "\n"
            "# Test Skill\n"
            "Use temporary scripts.\n"
        ),
    )

    registry = SkillRegistry.from_root(tmp_path / "skills")
    toolset = SkillToolset(registry)

    response = toolset.load_skill.func("coder", runtime=_tool_runtime())

    assert "Compatibility: Requires Python." in response
    assert "Allowed tools: write_workspace_file, run_workspace_code" in response
    assert "Use temporary scripts." in response


def test_run_skill_script_remains_available_without_workspace_permissions(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills" / "script-runner"
    _write_skill(
        skill_root,
        body=(
            "---\n"
            "name: script-runner\n"
            "description: Runs bundled scripts.\n"
            "---\n"
            "\n"
            "# Script Runner\n"
        ),
    )
    scripts_dir = skill_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "echo.py").write_text(
        "import sys\nprint('args=' + '|'.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )

    registry = SkillRegistry.from_root(tmp_path / "skills")
    toolset = SkillToolset(registry)

    response = toolset.run_skill_script.invoke(
        {
            "skill_name": "script-runner",
            "script_path": "scripts/echo.py",
            "script_args": ["one", "two"],
        }
    )

    assert "Exit code: 0" in response
    assert "args=one|two" in response
