"""Reproducibility metadata for evaluation and benchmark reports."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.evaluation import EvalRunManifest

SAFE_ENV_KEYS = (
    "CONTEXT_COMPRESSION_ENABLED",
    "CONTEXT_COMPRESSION_TRIGGER_TOKENS",
    "CONTEXT_COMPRESSION_KEEP_RECENT_TURNS",
    "WORKSPACE_EXECUTION_BACKEND",
    "OBSERVABILITY_ENABLED",
    "PROMETHEUS_ENABLED",
    "OTEL_ENABLED",
)


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
    allowed = ("provider", "model", "temperature", "top_p", "max_tokens", "judge_model")
    return {key: model[key] for key in allowed if model.get(key) is not None}


def build_run_manifest(
    *,
    cases_dir: Path,
    repository_root: Path | None = None,
    model: dict[str, Any] | None = None,
    commands: list[str] | None = None,
) -> EvalRunManifest:
    backend_root = repository_root or Path(__file__).resolve().parents[2]
    return EvalRunManifest(
        dataset_fingerprint=dataset_fingerprint(cases_dir),
        git_commit=git_commit(backend_root),
        environment=environment_summary(),
        model=sanitize_model_summary(model),
        commands=list(commands or []),
    )
