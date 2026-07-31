"""Reproducibility metadata for evaluation and benchmark reports."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.evaluation import EvalRunManifest

SAFE_ENV_KEYS = (
    "CONTEXT_COMPRESSION_ENABLED",
    "CONTEXT_COMPRESSION_TRIGGER_TOKENS",
    "CONTEXT_COMPRESSION_KEEP_RECENT_TURNS",
    "WORKSPACE_EXECUTION_BACKEND",
    "OBSERVABILITY_ENABLED",
    "PROMETHEUS_ENABLED",
    "OTEL_ENABLED",
    "STRUCTURED_FALLBACK_ENABLED",
    "STRUCTURED_WARMUP_ENABLED",
    "STRUCTURED_PROMPT_CACHE_ENABLED",
)

MODEL_ENV_ROLES = {
    "main": ("MODEL",),
    "structured": ("STRUCTED_MDOEL",),
    "fast": ("STRUCTURED_FAST_MODEL", "SMALL_MDOEL"),
    "small": ("SMALL_MDOEL",),
    "memory": ("MEMORY_MODEL", "STRUCTURED_FAST_MODEL", "STRUCTED_MDOEL", "SMALL_MDOEL", "MODEL"),
}


def dataset_fingerprint(cases_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(cases_dir.rglob("*.yaml")):
        digest.update(path.relative_to(cases_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def git_commit(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def git_source_state(repository_root: Path) -> tuple[bool, str]:
    """Fingerprint tracked changes and untracked source files without storing content."""
    try:
        status = subprocess.run(
            ["git", "-C", str(repository_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        diff = subprocess.run(
            ["git", "-C", str(repository_root), "diff", "--binary", "HEAD"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        untracked = subprocess.run(
            ["git", "-C", str(repository_root), "ls-files", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False, "unknown"

    digest = hashlib.sha256()
    digest.update(diff.stdout)
    for relative_name in sorted(line for line in untracked.stdout.splitlines() if line):
        relative_path = Path(relative_name)
        if relative_path.parts and relative_path.parts[0] == "storage":
            continue
        path = repository_root / relative_path
        if not path.is_file():
            continue
        digest.update(relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return bool(status.stdout.strip()), f"sha256:{digest.hexdigest()}"


def environment_summary() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "architecture": platform.machine(),
        "config": {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ},
    }


def sanitize_model_summary(model: dict[str, Any] | None) -> dict[str, Any]:
    if not model:
        return {}
    allowed = ("provider", "model", "models", "temperature", "top_p", "max_tokens", "judge_model")
    sanitized = {key: model[key] for key in allowed if model.get(key) is not None}
    if isinstance(sanitized.get("models"), dict):
        sanitized["models"] = {
            str(role): str(name)
            for role, name in sanitized["models"].items()
            if role in MODEL_ENV_ROLES and name
        }
    return sanitized


def model_summary_from_environment() -> dict[str, Any]:
    """Collect model names and provider host without exposing credentials."""
    models: dict[str, str] = {}
    for role, candidates in MODEL_ENV_ROLES.items():
        for key in candidates:
            value = (os.getenv(key) or "").strip()
            if value:
                models[role] = value
                break

    base_url = (os.getenv("BASE_URL") or os.getenv("STRUCTED_BASE_URL") or "").strip()
    host = urlparse(base_url).hostname or ""
    provider = "dashscope" if host.endswith("aliyuncs.com") else host or "unknown"
    return sanitize_model_summary(
        {
            "provider": provider,
            "model": models.get("main"),
            "models": models,
        }
    )


def build_run_manifest(
    *,
    cases_dir: Path,
    repository_root: Path | None = None,
    model: dict[str, Any] | None = None,
    commands: list[str] | None = None,
) -> EvalRunManifest:
    backend_root = repository_root or Path(__file__).resolve().parents[2]
    repository_dirty, source_fingerprint = git_source_state(backend_root)
    return EvalRunManifest(
        dataset_fingerprint=dataset_fingerprint(cases_dir),
        git_commit=git_commit(backend_root),
        repository_dirty=repository_dirty,
        source_fingerprint=source_fingerprint,
        environment=environment_summary(),
        model=sanitize_model_summary(model) if model is not None else model_summary_from_environment(),
        commands=list(commands or []),
    )
