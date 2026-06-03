from __future__ import annotations

import json
import locale
import logging
import os
import posixpath
import re
import shutil
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from langchain.tools import ToolRuntime, tool

from app.config import (
    get_daytona_api_key,
    get_daytona_api_url,
    get_daytona_auto_archive_interval_minutes,
    get_daytona_auto_delete_interval_minutes,
    get_daytona_auto_stop_interval_minutes,
    get_daytona_cleanup_policy,
    get_daytona_create_timeout_seconds,
    get_daytona_execution_timeout_seconds,
    get_daytona_file_sync_timeout_seconds,
    get_daytona_image,
    get_daytona_network_allow_list,
    get_daytona_network_block_all,
    get_daytona_remote_root,
    get_daytona_snapshot,
    get_daytona_target,
    get_file_storage_root,
    get_workspace_execution_backend,
)
from app.core.progress import emit_progress
from app.core.observability import (
    categorize_error,
    observation_sink_from_config,
    record_metric,
    run_context_from_config,
)

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
DAYTONA_SUPPORTED_CLEANUP_POLICIES = {"delete", "stop", "none"}

logger = logging.getLogger(__name__)


class WorkspaceValidationError(ValueError):
    """Raised when workspace access or execution is invalid."""


class WorkspaceExecutionError(RuntimeError):
    """Raised when the configured workspace execution backend fails."""


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


@dataclass(frozen=True)
class DaytonaExecutionSettings:
    api_key: str
    api_url: str
    target: str
    snapshot: str | None
    image: str | None
    cleanup_policy: Literal["delete", "stop", "none"]
    network_block_all: bool
    network_allow_list: str | None
    auto_stop_interval_minutes: int
    auto_archive_interval_minutes: int
    auto_delete_interval_minutes: int
    create_timeout_seconds: int
    execution_timeout_seconds: int
    file_sync_timeout_seconds: int
    remote_root: str

    @classmethod
    def from_environment(cls) -> "DaytonaExecutionSettings":
        api_key = (get_daytona_api_key() or "").strip()
        api_url = (get_daytona_api_url() or "").strip()
        target = (get_daytona_target() or "").strip()
        snapshot = (get_daytona_snapshot() or "").strip() or None
        image = (get_daytona_image() or "").strip() or None
        cleanup_policy = get_daytona_cleanup_policy()
        remote_root = get_daytona_remote_root().rstrip("/")

        missing: list[str] = []
        if not api_key:
            missing.append("DAYTONA_API_KEY")
        if not api_url:
            missing.append("DAYTONA_API_URL")
        if not target:
            missing.append("DAYTONA_TARGET")
        if missing:
            raise WorkspaceValidationError(
                "Daytona workspace execution is enabled but required settings are missing: "
                + ", ".join(missing)
            )
        if bool(snapshot) == bool(image):
            raise WorkspaceValidationError(
                "Set exactly one of DAYTONA_SNAPSHOT or DAYTONA_IMAGE when Daytona workspace "
                "execution is enabled."
            )
        if cleanup_policy not in DAYTONA_SUPPORTED_CLEANUP_POLICIES:
            raise WorkspaceValidationError(
                "DAYTONA_CLEANUP_POLICY must be one of: "
                + ", ".join(sorted(DAYTONA_SUPPORTED_CLEANUP_POLICIES))
            )
        if not remote_root.startswith("/"):
            raise WorkspaceValidationError("DAYTONA_REMOTE_ROOT must be an absolute sandbox path.")

        return cls(
            api_key=api_key,
            api_url=api_url,
            target=target,
            snapshot=snapshot,
            image=image,
            cleanup_policy=cleanup_policy,  # type: ignore[arg-type]
            network_block_all=get_daytona_network_block_all(),
            network_allow_list=get_daytona_network_allow_list(),
            auto_stop_interval_minutes=get_daytona_auto_stop_interval_minutes(),
            auto_archive_interval_minutes=get_daytona_auto_archive_interval_minutes(),
            auto_delete_interval_minutes=get_daytona_auto_delete_interval_minutes(),
            create_timeout_seconds=get_daytona_create_timeout_seconds(),
            execution_timeout_seconds=get_daytona_execution_timeout_seconds(),
            file_sync_timeout_seconds=get_daytona_file_sync_timeout_seconds(),
            remote_root=remote_root,
        )


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


def _get_configurable_value(config: Any, key: str) -> Any:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    return configurable.get(key)


def _remote_join(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part]
    if not cleaned:
        return "/"
    prefix = "/" if parts[0].startswith("/") else ""
    return prefix + posixpath.join(*cleaned)


def _quote_remote_path(path: str) -> str:
    return shlex.quote(path)


def _safe_log_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return text


def _daytona_error_category(exc: BaseException) -> str:
    name = exc.__class__.__name__
    if name == "DaytonaTimeoutError" or isinstance(exc, TimeoutError):
        return "timeout"
    if name in {"DaytonaAuthenticationError", "DaytonaAuthorizationError"}:
        return "authorization"
    if name == "DaytonaValidationError":
        return "validation"
    if name == "DaytonaConnectionError":
        return "connection"
    if name == "DaytonaRateLimitError":
        return "rate_limit"
    return "daytona_service"


def _is_daytona_timeout(exc: BaseException) -> bool:
    return _daytona_error_category(exc) == "timeout"


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
        config: Any | None = None,
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
        config: Any | None = None,
    ) -> WorkspaceExecutionResult:
        _ = config
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


class DaytonaExecutionBackend(ExecutionBackend):
    def __init__(
        self,
        *,
        settings: DaytonaExecutionSettings | None = None,
        daytona_factory: Any | None = None,
    ) -> None:
        self.settings = settings or DaytonaExecutionSettings.from_environment()
        self._daytona_factory = daytona_factory
        self._sdk_cache: dict[str, Any] | None = None

    def _load_sdk(self) -> dict[str, Any]:
        if self._sdk_cache is not None:
            return self._sdk_cache
        try:
            from daytona import (  # type: ignore[import-not-found]
                CreateSandboxFromImageParams,
                CreateSandboxFromSnapshotParams,
                Daytona,
                DaytonaConfig,
            )
        except ImportError as exc:
            raise WorkspaceValidationError(
                "Daytona workspace execution is enabled but the 'daytona' Python package "
                "is not installed."
            ) from exc

        self._sdk_cache = {
            "CreateSandboxFromImageParams": CreateSandboxFromImageParams,
            "CreateSandboxFromSnapshotParams": CreateSandboxFromSnapshotParams,
            "Daytona": Daytona,
            "DaytonaConfig": DaytonaConfig,
        }
        return self._sdk_cache

    def _create_client(self) -> Any:
        if self._daytona_factory is not None:
            return self._daytona_factory(self.settings)

        sdk = self._load_sdk()
        config = sdk["DaytonaConfig"](
            api_key=self.settings.api_key,
            api_url=self.settings.api_url,
            target=self.settings.target,
        )
        return sdk["Daytona"](config)

    def _build_labels(self, config: Any | None) -> dict[str, str]:
        labels = {
            "app": "smartclass",
            "purpose": "workspace-code",
        }
        for key in ("thread_id", "run_id", "plan_id", "agent_name"):
            value = _safe_log_value(_get_configurable_value(config, key))
            if value:
                labels[key] = _sanitize_identifier(value, fallback=key)
        return labels

    def _create_sandbox(self, client: Any, *, language: str, labels: dict[str, str]) -> Any:
        sdk = self._load_sdk() if self._daytona_factory is None else None
        sandbox_language = "javascript" if language == "node" else "python"
        env_vars = {
            "SMARTCLASS_BACKEND": "daytona",
            "SMARTCLASS_RUN_ID": labels.get("run_id", ""),
            "SMARTCLASS_THREAD_ID": labels.get("thread_id", ""),
        }
        network_kwargs: dict[str, Any] = {
            "network_block_all": self.settings.network_block_all,
        }
        if not self.settings.network_block_all and self.settings.network_allow_list:
            network_kwargs["network_allow_list"] = self.settings.network_allow_list

        common_kwargs = {
            "name": f"smartclass-{labels.get('run_id', 'adhoc-run')}",
            "language": sandbox_language,
            "labels": labels,
            "env_vars": env_vars,
            "auto_stop_interval": self.settings.auto_stop_interval_minutes,
            "auto_archive_interval": self.settings.auto_archive_interval_minutes,
            "auto_delete_interval": self.settings.auto_delete_interval_minutes,
            **network_kwargs,
        }
        if self._daytona_factory is not None:
            params = {
                **common_kwargs,
                "snapshot": self.settings.snapshot,
                "image": self.settings.image,
            }
        elif self.settings.snapshot:
            params_type = sdk["CreateSandboxFromSnapshotParams"] if sdk else None
            params = params_type(snapshot=self.settings.snapshot, **common_kwargs)
        else:
            params_type = sdk["CreateSandboxFromImageParams"] if sdk else None
            params = params_type(image=self.settings.image, **common_kwargs)
        return client.create(params, timeout=self.settings.create_timeout_seconds)

    def _remote_paths(self) -> tuple[str, str, str]:
        remote_root = self.settings.remote_root.rstrip("/")
        return (
            _remote_join(remote_root, "workspace"),
            _remote_join(remote_root, "run"),
            _remote_join(remote_root, "run", "outputs"),
        )

    def _ensure_remote_dirs(self, sandbox: Any, directories: set[str]) -> None:
        if not directories:
            return
        command = "mkdir -p " + " ".join(_quote_remote_path(path) for path in sorted(directories))
        response = sandbox.process.exec(command, timeout=30)
        if getattr(response, "exit_code", 1) != 0:
            raise WorkspaceExecutionError("Failed to prepare Daytona sandbox directories.")

    def _upload_workspace(self, sandbox: Any, *, paths: WorkspacePaths, remote_workspace: str) -> None:
        directories = {remote_workspace}
        files: list[tuple[Path, str]] = []
        if paths.workspace_root.exists():
            for local_path in sorted(paths.workspace_root.rglob("*")):
                if not local_path.is_file():
                    continue
                relative_path = local_path.relative_to(paths.workspace_root).as_posix()
                remote_path = _remote_join(remote_workspace, relative_path)
                directories.add(posixpath.dirname(remote_path))
                files.append((local_path, remote_path))

        self._ensure_remote_dirs(sandbox, directories)
        for local_path, remote_path in files:
            try:
                sandbox.fs.upload_file(
                    str(local_path),
                    remote_path,
                    timeout=self.settings.file_sync_timeout_seconds,
                )
            except TypeError:
                sandbox.fs.upload_file(
                    local_path.read_bytes(),
                    remote_path,
                    timeout=self.settings.file_sync_timeout_seconds,
                )

    def _collect_outputs(
        self,
        sandbox: Any,
        *,
        paths: WorkspacePaths,
        remote_output: str,
    ) -> list[str]:
        self._ensure_remote_dirs(sandbox, {remote_output})
        response = sandbox.process.exec(
            f"find {_quote_remote_path(remote_output)} -type f",
            timeout=30,
        )
        if getattr(response, "exit_code", 1) != 0:
            raise WorkspaceExecutionError("Failed to list Daytona sandbox output files.")

        stdout = getattr(getattr(response, "artifacts", None), "stdout", None)
        output = stdout if stdout is not None else getattr(response, "result", "")
        remote_files = [line.strip() for line in str(output).splitlines() if line.strip()]
        collected: list[str] = []
        for remote_path in remote_files:
            if not remote_path.startswith(remote_output.rstrip("/") + "/"):
                continue
            relative_remote = remote_path[len(remote_output.rstrip("/") + "/") :]
            local_path = paths.output_root / Path(*PurePosixPath(relative_remote).parts)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            downloaded = sandbox.fs.download_file(remote_path)
            if isinstance(downloaded, str):
                local_path.write_text(downloaded, encoding="utf-8")
            else:
                local_path.write_bytes(bytes(downloaded or b""))
            collected.append(local_path.relative_to(paths.thread_root).as_posix())
        return sorted(collected)

    def _cleanup(self, client: Any, sandbox: Any) -> None:
        _ = client
        if self.settings.cleanup_policy == "delete":
            sandbox.delete(timeout=self.settings.create_timeout_seconds)
        elif self.settings.cleanup_policy == "stop":
            sandbox.stop(timeout=self.settings.create_timeout_seconds)

    def execute(
        self,
        *,
        language: str,
        entrypoint: Path,
        paths: WorkspacePaths,
        config: Any | None = None,
    ) -> WorkspaceExecutionResult:
        started_at = time.monotonic()
        client = self._create_client()
        labels = self._build_labels(config)
        sandbox: Any | None = None
        remote_workspace, remote_run, remote_output = self._remote_paths()
        entrypoint_relative = entrypoint.relative_to(paths.workspace_root).as_posix()
        remote_entrypoint = _remote_join(remote_workspace, entrypoint_relative)
        command_name = "node" if language == "node" else "python"
        sandbox_name: str | None = None
        status = "failed"
        error_category: str | None = None

        try:
            sandbox = self._create_sandbox(client, language=language, labels=labels)
            sandbox_name = _safe_log_value(getattr(sandbox, "id", None)) or _safe_log_value(
                getattr(sandbox, "name", None)
            )
            self._ensure_remote_dirs(sandbox, {remote_workspace, remote_run, remote_output})
            self._upload_workspace(sandbox, paths=paths, remote_workspace=remote_workspace)

            env = {
                "AGENT_WORKSPACE_ROOT": remote_workspace,
                "AGENT_RUN_ROOT": remote_run,
                "AGENT_OUTPUT_DIR": remote_output,
                "PYTHONIOENCODING": "utf-8",
            }
            response = sandbox.process.exec(
                f"{command_name} {_quote_remote_path(remote_entrypoint)}",
                cwd=remote_workspace,
                env=env,
                timeout=self.settings.execution_timeout_seconds,
            )
            raw_stdout = getattr(getattr(response, "artifacts", None), "stdout", None)
            stdout, _ = _truncate_text(
                str(raw_stdout if raw_stdout is not None else getattr(response, "result", "")),
                max_chars=MAX_EXECUTION_OUTPUT_CHARS,
                max_lines=MAX_EXECUTION_OUTPUT_LINES,
            )
            raw_stderr = getattr(getattr(response, "artifacts", None), "stderr", None)
            stderr, _ = _truncate_text(
                str(raw_stderr if raw_stderr is not None else getattr(response, "stderr", "")),
                max_chars=MAX_EXECUTION_OUTPUT_CHARS,
                max_lines=MAX_EXECUTION_OUTPUT_LINES,
            )
            output_files = self._collect_outputs(
                sandbox,
                paths=paths,
                remote_output=remote_output,
            )
            exit_code = int(getattr(response, "exit_code", 1))
            timed_out = False
            status = "success" if exit_code == 0 else "nonzero_exit"
            return WorkspaceExecutionResult(
                language=language,
                entrypoint=entrypoint_relative,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                output_files=output_files,
                workspace_root=str(paths.workspace_root),
            )
        except Exception as exc:
            error_category = _daytona_error_category(exc)
            if _is_daytona_timeout(exc) and sandbox is not None:
                status = "timeout"
                return WorkspaceExecutionResult(
                    language=language,
                    entrypoint=entrypoint_relative,
                    exit_code=-1,
                    stdout="",
                    stderr="Daytona sandbox execution timed out.",
                    timed_out=True,
                    output_files=[],
                    workspace_root=str(paths.workspace_root),
                )
            message = (
                "Daytona sandbox workspace execution failed "
                f"({error_category}). Check backend logs for run diagnostics."
            )
            raise WorkspaceExecutionError(message) from exc
        finally:
            cleanup_error: BaseException | None = None
            if sandbox is not None:
                try:
                    self._cleanup(client, sandbox)
                except Exception as exc:
                    cleanup_error = exc
                    logger.warning(
                        "daytona_workspace_cleanup_failed",
                        extra={
                            "backend_type": "daytona",
                            "sandbox": sandbox_name,
                            "run_id": labels.get("run_id"),
                            "thread_id": labels.get("thread_id"),
                            "plan_id": labels.get("plan_id"),
                            "agent_name": labels.get("agent_name"),
                            "error_category": _daytona_error_category(exc),
                        },
                    )
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.info(
                "workspace_code_execution",
                extra={
                    "backend_type": "daytona",
                    "sandbox": sandbox_name,
                    "run_id": labels.get("run_id"),
                    "thread_id": labels.get("thread_id"),
                    "plan_id": labels.get("plan_id"),
                    "agent_name": labels.get("agent_name"),
                    "language": language,
                    "entrypoint": entrypoint_relative,
                    "duration_ms": duration_ms,
                    "status": status,
                    "error_category": error_category,
                    "cleanup_error": cleanup_error is not None,
                },
            )


def create_workspace_execution_backend() -> ExecutionBackend:
    backend = get_workspace_execution_backend()
    if backend == "local":
        return LocalSubprocessExecutionBackend()
    if backend == "daytona":
        return DaytonaExecutionBackend()
    raise WorkspaceValidationError(
        "WORKSPACE_EXECUTION_BACKEND must be one of: local, daytona."
    )


def _workspace_backend_name(backend: ExecutionBackend) -> str:
    if isinstance(backend, LocalSubprocessExecutionBackend):
        return "local"
    if isinstance(backend, DaytonaExecutionBackend):
        return "daytona"
    return backend.__class__.__name__


class WorkspaceManager:
    def __init__(self, backend: ExecutionBackend | None = None) -> None:
        self.backend = backend or create_workspace_execution_backend()

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

    def replace_text(
        self,
        config: Any,
        *,
        relative_path: str,
        old_text: str,
        new_text: str,
        count: int = 0,
    ) -> dict[str, Any]:
        if not old_text:
            raise WorkspaceValidationError("old_text must not be empty.")

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

        occurrences = content.count(old_text)
        if occurrences == 0:
            raise WorkspaceValidationError(
                f"Workspace file '{relative_path}' does not contain the requested old_text."
            )

        requested_count = count if count and count > 0 else occurrences
        replace_count = min(occurrences, requested_count)
        updated_content = content.replace(old_text, new_text, requested_count)
        resolved.write_text(updated_content, encoding="utf-8")
        return {
            "workspace_root": str(paths.workspace_root),
            "path": resolved.relative_to(paths.workspace_root).as_posix(),
            "occurrences_found": occurrences,
            "occurrences_replaced": replace_count,
        }

    def run_code(
        self,
        config: Any,
        *,
        language: Literal["python", "node"],
        entrypoint: str,
    ) -> WorkspaceExecutionResult:
        started_at = time.perf_counter()
        context = run_context_from_config(config).with_agent("workspace")
        sink = observation_sink_from_config(config)
        backend_type = _workspace_backend_name(self.backend)
        try:
            if language not in SUPPORTED_WORKSPACE_LANGUAGES:
                raise WorkspaceValidationError(
                    f"Unsupported workspace language '{language}'. "
                    f"Supported languages: {', '.join(sorted(SUPPORTED_WORKSPACE_LANGUAGES))}"
                )

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
        except Exception as exc:
            record_metric(
                "workspace.code_execution",
                context=context,
                sink=sink,
                status="failed",
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                fields={
                    "tool_name": "run_workspace_code",
                    "language": language,
                    "entrypoint": entrypoint,
                    "workspace_backend": backend_type,
                    "validation_phase": True,
                    "error_category": categorize_error(exc),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        try:
            result = self.backend.execute(
                language=language,
                entrypoint=resolved,
                paths=paths,
                config=config,
            )
        except Exception as exc:
            record_metric(
                "workspace.code_execution",
                context=context,
                sink=sink,
                status="failed",
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                fields={
                    "tool_name": "run_workspace_code",
                    "language": language,
                    "entrypoint": entrypoint,
                    "workspace_backend": backend_type,
                    "error_category": categorize_error(exc),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        status = "failed" if result.exit_code != 0 or result.timed_out else "success"
        record_metric(
            "workspace.code_execution",
            context=context,
            sink=sink,
            status=status,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            fields={
                "tool_name": "run_workspace_code",
                "language": result.language,
                "entrypoint": result.entrypoint,
                "workspace_backend": backend_type,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "output_file_count": len(result.output_files),
                "stdout_size": len(result.stdout or ""),
                "stderr_size": len(result.stderr or ""),
                "error_category": "timeout" if result.timed_out else None,
            },
        )
        return result


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
        def replace_workspace_text(
            relative_path: str,
            old_text: str,
            new_text: str,
            count: int = 0,
            *,
            runtime: ToolRuntime,
        ) -> str:
            """Replace exact UTF-8 text inside a workspace file."""
            emit_progress(
                runtime.config,
                "code_preparation",
                "running",
                detail=f"Replacing text in workspace file {relative_path}",
            )
            try:
                payload = self.manager.replace_text(
                    runtime.config,
                    relative_path=relative_path,
                    old_text=old_text,
                    new_text=new_text,
                    count=count,
                )
            except Exception:
                emit_progress(
                    runtime.config,
                    "code_preparation",
                    "failed",
                    detail=f"Failed to replace text in workspace file {relative_path}",
                )
                raise

            emit_progress(
                runtime.config,
                "code_preparation",
                "success",
                detail=f"Replaced text in workspace file {relative_path}",
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
        self.replace_workspace_text = replace_workspace_text
        self.run_workspace_code = run_workspace_code
        self.tools = [
            list_workspace_files,
            read_workspace_file,
            write_workspace_file,
            replace_workspace_text,
            run_workspace_code,
        ]
