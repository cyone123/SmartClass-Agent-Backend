from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from app.core.progress import ProgressTracker, emit_progress
from app.core.workspace import (
    DaytonaExecutionBackend,
    DaytonaExecutionSettings,
    LocalSubprocessExecutionBackend,
    WorkspaceManager,
    WorkspaceExecutionError,
    WorkspaceValidationError,
    _decode_process_output,
)


def _config() -> dict:
    return {
        "configurable": {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "plan_id": 123,
            "agent_name": "artifact-agent",
        }
    }


def _daytona_settings(**overrides: Any) -> DaytonaExecutionSettings:
    values = {
        "api_key": "test-key",
        "api_url": "https://daytona.example/api",
        "target": "test-target",
        "snapshot": "smartclass-test",
        "image": None,
        "cleanup_policy": "delete",
        "network_block_all": True,
        "network_allow_list": None,
        "auto_stop_interval_minutes": 15,
        "auto_archive_interval_minutes": 1440,
        "auto_delete_interval_minutes": 10080,
        "create_timeout_seconds": 60,
        "execution_timeout_seconds": 120,
        "file_sync_timeout_seconds": 1800,
        "remote_root": "/workspace/smartclass",
    }
    values.update(overrides)
    return DaytonaExecutionSettings(**values)


class _FakeArtifacts:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


class _FakeProcessResponse:
    def __init__(self, exit_code: int = 0, result: str = "", stderr: str = "") -> None:
        self.exit_code = exit_code
        self.result = result
        self.stderr = stderr
        self.artifacts = _FakeArtifacts(stdout=result, stderr=stderr)


class _FakeFileSystem:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.uploads: list[tuple[str, str]] = []
        self.downloads: list[str] = []

    def upload_file(self, source: str | bytes, remote_path: str, **kwargs: Any) -> None:
        _ = kwargs
        if isinstance(source, bytes):
            content = source
            source_label = "<bytes>"
        else:
            content = Path(source).read_bytes()
            source_label = source
        self.files[remote_path] = content
        self.uploads.append((source_label, remote_path))

    def download_file(self, remote_path: str, **kwargs: Any) -> bytes:
        _ = kwargs
        self.downloads.append(remote_path)
        return self.files[remote_path]


class _FakeProcess:
    def __init__(self, sandbox: "_FakeSandbox", scenario: str = "success") -> None:
        self.sandbox = sandbox
        self.scenario = scenario
        self.calls: list[dict[str, Any]] = []

    def exec(self, command: str, **kwargs: Any) -> _FakeProcessResponse:
        self.calls.append({"command": command, **kwargs})
        if command.startswith("mkdir -p"):
            return _FakeProcessResponse()
        if command.startswith("find "):
            output_dir = command.split(" ", 2)[1].strip("'\"")
            files = sorted(
                path for path in self.sandbox.fs.files if path.startswith(output_dir.rstrip("/") + "/")
            )
            return _FakeProcessResponse(result="\n".join(files))
        if self.scenario == "timeout":
            raise TimeoutError("timed out")
        if self.scenario == "service_error":
            raise RuntimeError("daytona unavailable")
        env = kwargs.get("env") or {}
        output_dir = env.get("AGENT_OUTPUT_DIR", "/workspace/smartclass/run/outputs")
        self.sandbox.last_execution = {"command": command, **kwargs}
        self.sandbox.fs.files[f"{output_dir}/result.txt"] = b"artifact"
        if self.scenario == "nonzero":
            return _FakeProcessResponse(exit_code=2, result="boom", stderr="failed")
        return _FakeProcessResponse(exit_code=0, result="done")


class _FakeSandbox:
    def __init__(self, scenario: str = "success", cleanup_error: bool = False) -> None:
        self.id = "sandbox-1"
        self.name = "smartclass-run-1"
        self.fs = _FakeFileSystem()
        self.process = _FakeProcess(self, scenario=scenario)
        self.deleted = False
        self.stopped = False
        self.cleanup_error = cleanup_error
        self.last_execution: dict[str, Any] | None = None

    def delete(self, **kwargs: Any) -> None:
        _ = kwargs
        if self.cleanup_error:
            raise RuntimeError("cleanup failed")
        self.deleted = True

    def stop(self, **kwargs: Any) -> None:
        _ = kwargs
        self.stopped = True


class _FakeDaytonaClient:
    def __init__(
        self,
        sandbox: _FakeSandbox | None = None,
        *,
        create_error: Exception | None = None,
    ) -> None:
        self.sandbox = sandbox or _FakeSandbox()
        self.create_error = create_error
        self.create_params: Any | None = None
        self.create_timeout: int | None = None

    def create(self, params: Any, **kwargs: Any) -> _FakeSandbox:
        if self.create_error is not None:
            raise self.create_error
        self.create_params = params
        self.create_timeout = kwargs.get("timeout")
        return self.sandbox


def test_workspace_manager_rejects_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager()

    with pytest.raises(WorkspaceValidationError):
        manager.write_file(_config(), relative_path="../escape.py", content="print('nope')")

    with pytest.raises(WorkspaceValidationError):
        manager.read_file(_config(), relative_path="C:/absolute.py")


def test_workspace_manager_defaults_to_local_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKSPACE_EXECUTION_BACKEND", raising=False)

    manager = WorkspaceManager()

    assert isinstance(manager.backend, LocalSubprocessExecutionBackend)


def test_workspace_manager_validates_daytona_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_EXECUTION_BACKEND", "daytona")
    for key in (
        "DAYTONA_API_KEY",
        "DAYTONA_API_URL",
        "DAYTONA_TARGET",
        "DAYTONA_SNAPSHOT",
        "DAYTONA_IMAGE",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(WorkspaceValidationError, match="DAYTONA_API_KEY"):
        WorkspaceManager()


def test_daytona_backend_uploads_executes_downloads_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    client = _FakeDaytonaClient()
    backend = DaytonaExecutionBackend(
        settings=_daytona_settings(),
        daytona_factory=lambda settings: client,
    )
    manager = WorkspaceManager(backend)
    manager.write_file(_config(), relative_path="input.txt", content="hello")
    manager.write_file(
        _config(),
        relative_path="generate.py",
        content=(
            "import os\n"
            "open(os.path.join(os.environ['AGENT_OUTPUT_DIR'], 'result.txt'), 'w').write('artifact')\n"
        ),
    )

    result = manager.run_code(_config(), language="python", entrypoint="generate.py")

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "done"
    assert result.output_files == ["runs/run-1/outputs/result.txt"]
    assert (tmp_path / "agent_workspaces" / "thread-1" / "runs" / "run-1" / "outputs" / "result.txt").read_text(
        encoding="utf-8"
    ) == "artifact"
    assert client.create_params["labels"]["run_id"] == "run-1"
    assert client.create_params["labels"]["thread_id"] == "thread-1"
    assert client.create_params["labels"]["plan_id"] == "123"
    assert client.create_params["labels"]["agent_name"] == "artifact-agent"
    assert client.create_params["network_block_all"] is True
    assert client.sandbox.deleted is True
    assert "/workspace/smartclass/workspace/generate.py" in client.sandbox.last_execution["command"]
    assert client.sandbox.last_execution["cwd"] == "/workspace/smartclass/workspace"
    assert client.sandbox.last_execution["env"]["AGENT_OUTPUT_DIR"] == "/workspace/smartclass/run/outputs"
    assert any(upload[1].endswith("/workspace/input.txt") for upload in client.sandbox.fs.uploads)


def test_daytona_backend_reports_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    sandbox = _FakeSandbox(scenario="nonzero")
    client = _FakeDaytonaClient(sandbox=sandbox)
    manager = WorkspaceManager(
        DaytonaExecutionBackend(
            settings=_daytona_settings(cleanup_policy="stop"),
            daytona_factory=lambda settings: client,
        )
    )
    manager.write_file(_config(), relative_path="bad.py", content="raise SystemExit(2)\n")

    result = manager.run_code(_config(), language="python", entrypoint="bad.py")

    assert result.exit_code == 2
    assert result.stderr == "failed"
    assert sandbox.stopped is True


def test_daytona_backend_reports_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    client = _FakeDaytonaClient(sandbox=_FakeSandbox(scenario="timeout"))
    manager = WorkspaceManager(
        DaytonaExecutionBackend(
            settings=_daytona_settings(cleanup_policy="none"),
            daytona_factory=lambda settings: client,
        )
    )
    manager.write_file(_config(), relative_path="sleep.py", content="import time\ntime.sleep(999)\n")

    result = manager.run_code(_config(), language="python", entrypoint="sleep.py")

    assert result.timed_out is True
    assert result.exit_code == -1
    assert "timed out" in result.stderr


def test_daytona_backend_raises_service_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    client = _FakeDaytonaClient(create_error=RuntimeError("service unavailable"))
    manager = WorkspaceManager(
        DaytonaExecutionBackend(
            settings=_daytona_settings(),
            daytona_factory=lambda settings: client,
        )
    )
    manager.write_file(_config(), relative_path="hello.py", content="print('hello')\n")

    with pytest.raises(WorkspaceExecutionError, match="daytona_service"):
        manager.run_code(_config(), language="python", entrypoint="hello.py")


def test_daytona_backend_cleanup_failure_does_not_mask_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    client = _FakeDaytonaClient(sandbox=_FakeSandbox(cleanup_error=True))
    manager = WorkspaceManager(
        DaytonaExecutionBackend(
            settings=_daytona_settings(),
            daytona_factory=lambda settings: client,
        )
    )
    manager.write_file(_config(), relative_path="hello.py", content="print('hello')\n")

    result = manager.run_code(_config(), language="python", entrypoint="hello.py")

    assert result.exit_code == 0


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


def test_workspace_manager_local_backend_collects_html_artifact_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager(LocalSubprocessExecutionBackend())
    manager.write_file(
        _config(),
        relative_path="generate_html.py",
        content=(
            "import os\n"
            "output = os.path.join(os.environ['AGENT_OUTPUT_DIR'], 'game.html')\n"
            "open(output, 'w', encoding='utf-8').write('<html></html>')\n"
        ),
    )

    result = manager.run_code(_config(), language="python", entrypoint="generate_html.py")

    assert result.exit_code == 0
    assert "runs/run-1/outputs/game.html" in result.output_files
    output_path = tmp_path / "agent_workspaces" / "thread-1" / "runs" / "run-1" / "outputs" / "game.html"
    assert output_path.read_text(encoding="utf-8") == "<html></html>"


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


def test_workspace_manager_rejects_unsupported_language_before_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager(LocalSubprocessExecutionBackend())
    manager.write_file(_config(), relative_path="script.rb", content="puts 'nope'\n")

    with pytest.raises(WorkspaceValidationError, match="Unsupported workspace language"):
        manager.run_code(_config(), language="ruby", entrypoint="script.rb")  # type: ignore[arg-type]


def test_workspace_manager_replaces_targeted_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    manager = WorkspaceManager()
    manager.write_file(
        _config(),
        relative_path="index.html",
        content="<h1>Old title</h1><p>Old title</p>",
    )

    result = manager.replace_text(
        _config(),
        relative_path="index.html",
        old_text="Old title",
        new_text="New title",
        count=1,
    )

    assert result["occurrences_found"] == 2
    assert result["occurrences_replaced"] == 1
    content = manager.read_file(_config(), relative_path="index.html")["content"]
    assert "<h1>New title</h1>" in content
    assert "<p>Old title</p>" in content


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


def test_progress_tracker_accepts_revision_step_keys() -> None:
    tracker = ProgressTracker(run_id="run-1")

    payload = tracker.update(
        "artifact_revision_routing",
        "running",
        detail="Routing artifact revision request",
    )
    tracker.update("artifact_revision_prepare", "success", detail="Workspace ready")
    tracker.update("ppt_revision", "success", detail="PPT updated")
    tracker.update("artifact_fan_in", "success", detail="Revision summary ready")

    step_keys = [step["step_key"] for step in payload["steps"]]
    assert "artifact_revision_routing" in step_keys


def test_workspace_backend_decodes_non_utf8_process_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_EXECUTION_BACKEND", "local")
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
