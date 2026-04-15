from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.core.progress import emit_progress
from app.core.workspace import (
    LocalSubprocessExecutionBackend,
    WorkspaceManager,
    WorkspaceValidationError,
    _decode_process_output,
)


def _config() -> dict:
    return {"configurable": {"thread_id": "thread-1", "run_id": "run-1"}}


def test_workspace_manager_rejects_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager()

    with pytest.raises(WorkspaceValidationError):
        manager.write_file(_config(), relative_path="../escape.py", content="print('nope')")

    with pytest.raises(WorkspaceValidationError):
        manager.read_file(_config(), relative_path="C:/absolute.py")


def test_workspace_manager_runs_python_and_truncates_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager()
    manager.write_file(
        _config(),
        relative_path="hello.py",
        content="for i in range(250):\n    print(f'line-{i}')\n",
    )

    result = manager.run_code(_config(), language="python", entrypoint="hello.py")

    assert result.exit_code == 0
    assert "line-0" in result.stdout
    assert "...[truncated]" in result.stdout


def test_workspace_manager_times_out_long_running_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager(LocalSubprocessExecutionBackend(timeout_seconds=1))
    manager.write_file(
        _config(),
        relative_path="sleep.py",
        content="import time\ntime.sleep(2)\n",
    )

    result = manager.run_code(_config(), language="python", entrypoint="sleep.py")

    assert result.timed_out is True
    assert result.exit_code == -1


def test_workspace_manager_rejects_dependency_installers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager()
    manager.write_file(
        _config(),
        relative_path="bad.py",
        content="import os\nos.system('pip install pptxgenjs')\n",
    )

    with pytest.raises(WorkspaceValidationError):
        manager.run_code(_config(), language="python", entrypoint="bad.py")


def test_emit_progress_is_silent_without_registered_reporter(capsys: pytest.CaptureFixture[str]) -> None:
    emitted = emit_progress(
        {"configurable": {"thread_id": "thread-1", "run_id": "artifact-docx-run"}},
        "code_preparation",
        "running",
        detail="Writing workspace file generate_lesson_plan.js",
    )

    captured = capsys.readouterr()
    assert emitted is None
    assert captured.out == ""
    assert captured.err == ""


def test_workspace_backend_decodes_non_utf8_process_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager()
    manager.write_file(
        _config(),
        relative_path="test.js",
        content="console.log('ok')\n",
    )

    fake_output = "生成完成".encode("utf-8") + b"\xac"

    def fake_run(*args, **kwargs):
        _ = args, kwargs
        return CompletedProcess(
            args=["node", "test.js"],
            returncode=0,
            stdout=fake_output,
            stderr=b"",
        )

    monkeypatch.setattr("app.core.workspace.subprocess.run", fake_run)

    result = manager.run_code(_config(), language="node", entrypoint="test.js")

    assert result.exit_code == 0
    assert "生成完成" in result.stdout
    assert "\ufffd" in result.stdout
    assert result.stderr == ""


def test_decode_process_output_falls_back_without_raising() -> None:
    decoded = _decode_process_output("生成完成".encode("utf-8") + b"\xac")
    assert "生成完成" in decoded
