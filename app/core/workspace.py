from __future__ import annotations

import json
import locale
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from langchain.tools import ToolRuntime, tool

from app.config import get_file_storage_root
from app.core.progress import emit_progress

DEFAULT_EXECUTION_TIMEOUT_SECONDS = 30
MAX_EXECUTION_OUTPUT_CHARS = 12000
MAX_EXECUTION_OUTPUT_LINES = 200
MAX_FILE_READ_CHARS = 12000
MAX_FILE_READ_LINES = 200
SUPPORTED_WORKSPACE_LANGUAGES = {"python", "node"}
INSTALLER_COMMAND_PATTERN = re.compile(
    r"(?i)\b(pip|pip3|python\s+-m\s+pip|npm|npx|pnpm|yarn)\s+"
    r"(install|add|i|dlx)\b"
)
SAFE_WORKSPACE_ID_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class WorkspaceValidationError(ValueError):
    """Raised when workspace access or execution is invalid."""


@dataclass(frozen=True)
class WorkspacePaths:
    thread_root: Path
    workspace_root: Path
    run_root: Path
    output_root: Path


@dataclass(frozen=True)
class WorkspaceExecutionResult:
    language: str
    entrypoint: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    output_files: list[str]
    workspace_root: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sanitize_identifier(value: str | None, *, fallback: str) -> str:
    normalized = SAFE_WORKSPACE_ID_PATTERN.sub("-", (value or "").strip()).strip("-._")
    return normalized or fallback


def _truncate_text(
    text: str,
    *,
    max_chars: int,
    max_lines: int,
) -> tuple[str, bool]:
    if not text:
        return "", False

    lines = text.splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars]
        truncated = True

    if truncated:
        result = f"{result}\n...[truncated]"
    return result, truncated


def _decode_process_output(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw

    tried: set[str] = set()
    for encoding in (
        "utf-8",
        locale.getpreferredencoding(False),
        "gbk",
    ):
        normalized = (encoding or "").strip()
        if not normalized or normalized in tried:
            continue
        tried.add(normalized)
        try:
            return raw.decode(normalized)
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="replace")


def _snapshot_files(root: Path) -> dict[str, float]:
    if not root.exists():
        return {}

    snapshot: dict[str, float] = {}
    for path in root.rglob("*"):
        if path.is_file():
            snapshot[str(path)] = path.stat().st_mtime
    return snapshot


def _list_changed_files(
    before: dict[str, float],
    after: dict[str, float],
    *,
    relative_to: Path,
) -> list[str]:
    changed: list[str] = []
    for raw_path, mtime in after.items():
        if before.get(raw_path) != mtime:
            path = Path(raw_path)
            changed.append(path.relative_to(relative_to).as_posix())
    return sorted(changed)


def get_workspace_paths(config: Any) -> WorkspacePaths:
    configurable = {}
    if isinstance(config, dict):
        maybe_configurable = config.get("configurable")
        if isinstance(maybe_configurable, dict):
            configurable = maybe_configurable

    thread_id = _sanitize_identifier(
        configurable.get("thread_id"),
        fallback="default-thread",
    )
    run_id = _sanitize_identifier(
        configurable.get("run_id"),
        fallback="adhoc-run",
    )

    thread_root = get_file_storage_root() / "agent_workspaces" / thread_id
    workspace_root = thread_root / "workspace"
    run_root = thread_root / "runs" / run_id
    output_root = run_root / "outputs"

    workspace_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    return WorkspacePaths(
        thread_root=thread_root,
        workspace_root=workspace_root,
        run_root=run_root,
        output_root=output_root,
    )


def _resolve_workspace_path(
    workspace_root: Path,
    relative_path: str,
    *,
    allow_directory: bool = False,
) -> Path:
    if not relative_path:
        raise WorkspaceValidationError("Path must not be empty.")

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise WorkspaceValidationError("Absolute paths are not allowed in the workspace.")

    resolved = (workspace_root / candidate).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise WorkspaceValidationError(
            "Path traversal outside the workspace is not allowed."
        ) from exc

    if resolved.exists():
        if resolved.is_dir() and not allow_directory:
            raise WorkspaceValidationError("Expected a file path, but a directory was provided.")
    return resolved


def _build_execution_env(paths: WorkspacePaths) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in (
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "SYSTEMROOT",
        "ComSpec",
        "COMSPEC",
        "WINDIR",
        "TEMP",
        "TMP",
    ):
        value = os.environ.get(key)
        if value:
            env[key] = value

    env.update(
        {
            "AGENT_WORKSPACE_ROOT": str(paths.workspace_root),
            "AGENT_RUN_ROOT": str(paths.run_root),
            "AGENT_OUTPUT_DIR": str(paths.output_root),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _resolve_command(language: str) -> list[str]:
    if language == "python":
        return [sys.executable]
    if language == "node":
        node_path = shutil.which("node")
        if not node_path:
            raise WorkspaceValidationError("Node.js is not available on the host.")
        return [node_path]
    raise WorkspaceValidationError(
        f"Unsupported workspace language '{language}'. "
        f"Supported languages: {', '.join(sorted(SUPPORTED_WORKSPACE_LANGUAGES))}"
    )


class ExecutionBackend:
    def execute(
        self,
        *,
        language: str,
        entrypoint: Path,
        paths: WorkspacePaths,
    ) -> WorkspaceExecutionResult:
        raise NotImplementedError


class LocalSubprocessExecutionBackend(ExecutionBackend):
    def __init__(self, *, timeout_seconds: int = DEFAULT_EXECUTION_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def execute(
        self,
        *,
        language: str,
        entrypoint: Path,
        paths: WorkspacePaths,
    ) -> WorkspaceExecutionResult:
        command = _resolve_command(language)
        command.append(str(entrypoint))

        before_workspace = _snapshot_files(paths.workspace_root)
        before_output = _snapshot_files(paths.output_root)
        env = _build_execution_env(paths)

        try:
            completed = subprocess.run(
                command,
                cwd=paths.workspace_root,
                capture_output=True,
                text=False,
                timeout=self.timeout_seconds,
                check=False,
                env=env,
            )
            stdout, _ = _truncate_text(
                _decode_process_output(completed.stdout),
                max_chars=MAX_EXECUTION_OUTPUT_CHARS,
                max_lines=MAX_EXECUTION_OUTPUT_LINES,
            )
            stderr, _ = _truncate_text(
                _decode_process_output(completed.stderr),
                max_chars=MAX_EXECUTION_OUTPUT_CHARS,
                max_lines=MAX_EXECUTION_OUTPUT_LINES,
            )
            timed_out = False
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, _ = _truncate_text(
                _decode_process_output(exc.stdout),
                max_chars=MAX_EXECUTION_OUTPUT_CHARS,
                max_lines=MAX_EXECUTION_OUTPUT_LINES,
            )
            stderr, _ = _truncate_text(
                _decode_process_output(exc.stderr),
                max_chars=MAX_EXECUTION_OUTPUT_CHARS,
                max_lines=MAX_EXECUTION_OUTPUT_LINES,
            )
            timed_out = True
            exit_code = -1

        after_workspace = _snapshot_files(paths.workspace_root)
        after_output = _snapshot_files(paths.output_root)
        output_files = sorted(
            {
                *(
                    _list_changed_files(
                        before_workspace,
                        after_workspace,
                        relative_to=paths.thread_root,
                    )
                ),
                *(
                    _list_changed_files(
                        before_output,
                        after_output,
                        relative_to=paths.thread_root,
                    )
                ),
            }
        )

        return WorkspaceExecutionResult(
            language=language,
            entrypoint=entrypoint.relative_to(paths.workspace_root).as_posix(),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            output_files=output_files,
            workspace_root=str(paths.workspace_root),
        )


class WorkspaceManager:
    def __init__(self, backend: ExecutionBackend | None = None) -> None:
        self.backend = backend or LocalSubprocessExecutionBackend()

    def list_files(self, config: Any, *, relative_path: str = ".") -> dict[str, Any]:
        paths = get_workspace_paths(config)
        target = _resolve_workspace_path(
            paths.workspace_root,
            relative_path,
            allow_directory=True,
        )
        if not target.exists():
            raise WorkspaceValidationError(f"Workspace path '{relative_path}' was not found.")
        if not target.is_dir():
            raise WorkspaceValidationError(f"Workspace path '{relative_path}' is not a directory.")

        entries = []
        for path in sorted(target.rglob("*")):
            if path.is_file():
                entries.append(path.relative_to(paths.workspace_root).as_posix())

        return {
            "workspace_root": str(paths.workspace_root),
            "base_path": target.relative_to(paths.workspace_root).as_posix(),
            "files": entries,
        }

    def read_file(self, config: Any, *, relative_path: str) -> dict[str, Any]:
        paths = get_workspace_paths(config)
        resolved = _resolve_workspace_path(paths.workspace_root, relative_path)
        if not resolved.is_file():
            raise WorkspaceValidationError(f"Workspace file '{relative_path}' was not found.")

        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceValidationError(
                f"Workspace file '{relative_path}' is not UTF-8 text."
            ) from exc

        truncated_content, truncated = _truncate_text(
            content,
            max_chars=MAX_FILE_READ_CHARS,
            max_lines=MAX_FILE_READ_LINES,
        )
        return {
            "workspace_root": str(paths.workspace_root),
            "path": resolved.relative_to(paths.workspace_root).as_posix(),
            "content": truncated_content,
            "truncated": truncated,
        }

    def write_file(
        self,
        config: Any,
        *,
        relative_path: str,
        content: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        paths = get_workspace_paths(config)
        resolved = _resolve_workspace_path(paths.workspace_root, relative_path)
        if resolved.exists() and not overwrite:
            raise WorkspaceValidationError(
                f"Workspace file '{relative_path}' already exists. Set overwrite=true to replace it."
            )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {
            "workspace_root": str(paths.workspace_root),
            "path": resolved.relative_to(paths.workspace_root).as_posix(),
            "bytes_written": len(content.encode("utf-8")),
            "overwrite": overwrite,
        }

    def run_code(
        self,
        config: Any,
        *,
        language: Literal["python", "node"],
        entrypoint: str,
    ) -> WorkspaceExecutionResult:
        paths = get_workspace_paths(config)
        resolved = _resolve_workspace_path(paths.workspace_root, entrypoint)
        if not resolved.is_file():
            raise WorkspaceValidationError(f"Workspace file '{entrypoint}' was not found.")

        source = resolved.read_text(encoding="utf-8")
        if INSTALLER_COMMAND_PATTERN.search(source):
            raise WorkspaceValidationError(
                "Dependency installation commands are disabled in workspace code. "
                "Rely on host-managed dependencies declared in the skill compatibility notes."
            )

        return self.backend.execute(
            language=language,
            entrypoint=resolved,
            paths=paths,
        )


class WorkspaceToolset:
    def __init__(self, manager: WorkspaceManager | None = None) -> None:
        self.manager = manager or WorkspaceManager()

        @tool
        def list_workspace_files(
            relative_path: str = ".",
            *,
            runtime: ToolRuntime,
        ) -> str:
            """List UTF-8 workspace files available to the active skill."""
            payload = self.manager.list_files(runtime.config, relative_path=relative_path)
            return json.dumps(payload, ensure_ascii=False)

        @tool
        def read_workspace_file(
            relative_path: str,
            *,
            runtime: ToolRuntime,
        ) -> str:
            """Read a UTF-8 text file from the active workspace."""
            payload = self.manager.read_file(runtime.config, relative_path=relative_path)
            return json.dumps(payload, ensure_ascii=False)

        @tool
        def write_workspace_file(
            relative_path: str,
            content: str,
            overwrite: bool = False,
            *,
            runtime: ToolRuntime,
        ) -> str:
            """Write a UTF-8 file into the active workspace."""
            emit_progress(
                runtime.config,
                "code_preparation",
                "running",
                detail=f"Writing workspace file {relative_path}",
            )
            try:
                payload = self.manager.write_file(
                    runtime.config,
                    relative_path=relative_path,
                    content=content,
                    overwrite=overwrite,
                )
            except Exception:
                emit_progress(
                    runtime.config,
                    "code_preparation",
                    "failed",
                    detail=f"Failed to write workspace file {relative_path}",
                )
                raise

            emit_progress(
                runtime.config,
                "code_preparation",
                "success",
                detail=f"Wrote workspace file {relative_path}",
            )
            return json.dumps(payload, ensure_ascii=False)

        @tool
        def run_workspace_code(
            language: Literal["python", "node"],
            entrypoint: str,
            *,
            runtime: ToolRuntime,
        ) -> str:
            """Execute a Python or Node.js file from the active workspace."""
            emit_progress(
                runtime.config,
                "code_execution",
                "running",
                detail=f"Running {entrypoint} with {language}",
            )
            try:
                result = self.manager.run_code(
                    runtime.config,
                    language=language,
                    entrypoint=entrypoint,
                )
            except Exception as exc:
                emit_progress(
                    runtime.config,
                    "code_execution",
                    "failed",
                    detail=str(exc),
                )
                raise

            emit_progress(
                runtime.config,
                "code_execution",
                "success" if result.exit_code == 0 and not result.timed_out else "failed",
                detail=f"Executed {entrypoint} with exit code {result.exit_code}",
            )
            return json.dumps(result.to_dict(), ensure_ascii=False)

        self.list_workspace_files = list_workspace_files
        self.read_workspace_file = read_workspace_file
        self.write_workspace_file = write_workspace_file
        self.run_workspace_code = run_workspace_code
        self.tools = [
            list_workspace_files,
            read_workspace_file,
            write_workspace_file,
            run_workspace_code,
        ]
