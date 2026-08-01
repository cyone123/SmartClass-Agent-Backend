from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import yaml
from dotenv import dotenv_values

from tests.benchmarks.artifact_validation import ArtifactType, ValidationResult, validate_artifact

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPES: tuple[ArtifactType, ...] = ("ppt", "docx", "html-game")
STATE_KEYS: dict[ArtifactType, str] = {
    "ppt": "ppt_result",
    "docx": "lesson_plan_result",
    "html-game": "game_result",
}
PHASE_CASE_COUNTS = {"smoke": 1, "pilot": 2, "formal": 5}
PHASE_REPEATS = {"smoke": 1, "pilot": 1, "formal": 2}

BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = BACKEND_ROOT.parent
CASES_PATH = Path(__file__).with_name("artifact_cases.yaml")
RAW_RESULTS_DIR = BACKEND_ROOT / "tests" / "evals" / "results"
ARTIFACT_EXPORT_ROOT = BACKEND_ROOT / "storage" / "benchmarks" / "artifact_generation"
BASELINES_ROOT = WORKSPACE_ROOT / "docs" / "benchmarks" / "baselines"


@dataclass(frozen=True)
class ArtifactCase:
    case_id: str
    subject: str
    grade: str
    topic: str
    duration_minutes: int
    objectives: tuple[str, ...]
    required_term_groups: tuple[tuple[str, ...], ...]
    open_question: str
    plan: str


class MemorySink:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


def configure_local_docker_services(env_file: Path) -> None:
    values = dotenv_values(env_file)
    required = (
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "MINIO_API_PORT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
    )
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise RuntimeError("Missing local Docker settings: " + ", ".join(missing))
    os.environ.update(
        {
            "DB_HOST": "127.0.0.1",
            "DB_PORT": str(values["POSTGRES_PORT"]),
            "DB_USER": str(values["POSTGRES_USER"]),
            "DB_PASSWORD": str(values["POSTGRES_PASSWORD"]),
            "DB_NAME": str(values["POSTGRES_DB"]),
            "STORAGE_BACKEND": "minio",
            "MINIO_ENDPOINT": f"127.0.0.1:{values['MINIO_API_PORT']}",
            "MINIO_ACCESS_KEY": str(values["MINIO_ACCESS_KEY"]),
            "MINIO_SECRET_KEY": str(values["MINIO_SECRET_KEY"]),
            "MINIO_BUCKET": str(values["MINIO_BUCKET"]),
            "MINIO_SECURE": "false",
            "FILE_STORAGE_ROOT": str(BACKEND_ROOT / "storage"),
            "WORKSPACE_EXECUTION_BACKEND": "local",
            "OTEL_ENABLED": "false",
            "PROMETHEUS_ENABLED": "false",
            "OBSERVABILITY_TRACE_JSONL_ENABLED": "false",
        }
    )


def configure_model_environment(env_file: Path, *, profile: str = "main") -> None:
    values = dotenv_values(env_file)
    profiles = {
        "main": ("MODEL", "API_KEY", "BASE_URL"),
        "structured": ("STRUCTED_MDOEL", "STRUCTED_API_KEY", "STRUCTED_BASE_URL"),
        "small": ("SMALL_MDOEL", "SMALL_API_KEY", "SMALL_BASE_URL"),
    }
    source_names = profiles[profile]
    missing = [name for name in source_names if not values.get(name)]
    if missing:
        raise RuntimeError("Missing model settings: " + ", ".join(missing))
    for target, source in zip(("MODEL", "API_KEY", "BASE_URL"), source_names, strict=True):
        os.environ[target] = str(values[source])


def load_cases(path: Path = CASES_PATH) -> list[ArtifactCase]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported artifact case schema: {payload.get('schema_version')}")
    raw_cases = payload.get("cases") or []
    cases: list[ArtifactCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        case_id = str(raw["case_id"])
        if case_id in seen:
            raise ValueError(f"Duplicate artifact case id: {case_id}")
        seen.add(case_id)
        groups = tuple(tuple(str(term) for term in group) for group in raw["required_term_groups"])
        if not groups or any(not group for group in groups):
            raise ValueError(f"Case {case_id} must define non-empty required term groups")
        cases.append(
            ArtifactCase(
                case_id=case_id,
                subject=str(raw["subject"]),
                grade=str(raw["grade"]),
                topic=str(raw["topic"]),
                duration_minutes=int(raw["duration_minutes"]),
                objectives=tuple(str(item) for item in raw["objectives"]),
                required_term_groups=groups,
                open_question=str(raw["open_question"]),
                plan=str(raw["plan"]),
            )
        )
    if len(cases) != 5:
        raise ValueError(f"Expected exactly 5 artifact cases, found {len(cases)}")
    return cases


def cases_fingerprint(path: Path = CASES_PATH) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _percent(numerator: float, denominator: float) -> float:
    return round(numerator * 100 / denominator, 2) if denominator else 0.0


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(float(ordered[index]), 2)


def _safe_error(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re_sub_sensitive(text)
    return text[:1000]


def re_sub_sensitive(text: str) -> str:
    import re

    text = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(api[_-]?key|access[_-]?token|secret|password)=([^\s&]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"[A-Za-z]:\\[^\r\n]+", "[REDACTED_PATH]", text)
    return text


def classify_failure(error: str | None) -> str | None:
    if not error:
        return None
    lowered = error.casefold()
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "pptxgenjs" in lowered or "cannot find module" in lowered or "dependency" in lowered:
        return "dependency"
    if "no generated artifact" in lowered or "no artifact file" in lowered:
        return "no_output"
    if "minio" in lowered or "storage" in lowered or "upload" in lowered:
        return "storage"
    if "database" in lowered or "postgres" in lowered or "sqlalchemy" in lowered:
        return "database"
    if "workspace" in lowered or "exit code" in lowered:
        return "workspace"
    if "model" in lowered or "openai" in lowered or "api" in lowered or "connection error" in lowered:
        return "model"
    return "unknown"


def build_state(case: ArtifactCase, *, plan_id: int, repeat: int) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage

    objectives = "；".join(case.objectives)
    request = (
        f"请为{case.grade}{case.subject}《{case.topic}》生成教学产物，课时{case.duration_minutes}分钟。"
        f"教学目标：{objectives}。必须忠实覆盖教学方案中的核心术语和评价要求。"
        "PPT 使用 16:9 且控制在 8-12 页；DOCX 应有目标、重难点、流程、评价和课后任务；"
        "HTML 必须是自包含单文件，提供可操作控件与即时反馈。"
    )
    return {
        "messages": [HumanMessage(id=f"benchmark-{case.case_id}-{repeat}", content=request)],
        "plan_id": plan_id,
        "teaching_metadata": {
            "subject": case.subject,
            "grade": case.grade,
            "topic": case.topic,
            "duration_minutes": case.duration_minutes,
            "objectives": list(case.objectives),
            "open_question": case.open_question,
        },
        "teaching_design_plan": case.plan,
        "rag_context": "本实验不注入外部资料，只允许使用固定教学方案中的事实。",
        "profile_memory_context": "偏好结构清晰、可直接用于课堂的中文产物。",
        "experience_memory_context": "活动必须包含可观察的形成性评价证据。",
    }


def _observation_metrics(events: Sequence[Any], sub_run_id: str) -> dict[str, Any]:
    selected = [event for event in events if getattr(getattr(event, "context", None), "run_id", None) == sub_run_id]
    llm_events = [event for event in selected if getattr(event, "event", None) == "llm.call"]
    tool_events = [event for event in selected if getattr(event, "event", None) == "tool.invoke"]
    workspace_events = [event for event in selected if getattr(event, "event", None) == "workspace.code_execution"]
    generation_events = [
        event
        for event in selected
        if getattr(event, "event", None) == "artifact.generate" and getattr(event, "kind", None) == "metric"
    ]
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    usage_events = 0
    for event in llm_events:
        if event.fields.get("token_usage_available"):
            usage_events += 1
        for key in usage:
            value = event.fields.get(key)
            if isinstance(value, int):
                usage[key] += value
    duration = generation_events[-1].duration_ms if generation_events else None
    return {
        "duration_ms": duration,
        "llm_call_count": len(llm_events),
        "llm_failed_call_count": sum(event.status == "failed" for event in llm_events),
        "llm_usage_event_count": usage_events,
        **usage,
        "tool_call_count": len(tool_events),
        "tool_failed_call_count": sum(event.status == "failed" for event in tool_events),
        "workspace_execution_count": len(workspace_events),
        "workspace_failed_execution_count": sum(event.status == "failed" for event in workspace_events),
    }


async def _ensure_benchmark_entities(*, experiment_id: str, case: ArtifactCase, repeat: int) -> tuple[int, int, str]:
    from sqlalchemy import select

    from app.dependencies.db import AsyncSessionLocal
    from app.models.plan import Plan
    from app.models.session import Session
    from app.models.user import User

    username = "artifact_benchmark"
    thread_id = f"artifact-benchmark-{experiment_id}-{case.case_id}-r{repeat}"
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if user is None:
            user = User(
                username=username,
                password_hash="benchmark-account-no-login",
                display_name="Artifact Benchmark",
                role="teacher",
                is_active=False,
            )
            db.add(user)
            await db.flush()
        plan = Plan(user_id=user.id, name=f"Benchmark {case.case_id} r{repeat}")
        db.add(plan)
        await db.flush()
        session = Session(
            name=f"Benchmark {case.topic}",
            thread_id=thread_id,
            user_id=user.id,
            plan_id=plan.id,
        )
        db.add(session)
        await db.commit()
        return user.id, plan.id, thread_id


async def _load_artifact_record(artifact_id: int, user_id: int) -> Any:
    from app.dependencies.db import AsyncSessionLocal
    from app.services.artifact_service import require_artifact_by_id

    async with AsyncSessionLocal() as db:
        return await require_artifact_by_id(db, artifact_id, user_id=user_id)


async def _recover_failed_artifact_record(
    *,
    thread_id: str,
    artifact_type: ArtifactType,
    user_id: int,
    error: str,
) -> Any | None:
    """Resolve and close a record when the outer benchmark timeout cancels the node."""

    from sqlalchemy import select

    from app.dependencies.db import AsyncSessionLocal
    from app.models.file import ArtifactFile
    from app.services.artifact_service import mark_artifact_failed

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ArtifactFile)
            .where(
                ArtifactFile.thread_id == thread_id,
                ArtifactFile.artifact_type == artifact_type,
                ArtifactFile.user_id == user_id,
            )
            .order_by(ArtifactFile.id.desc())
        )
        artifact = result.scalars().first()
        if artifact is not None and artifact.status == "running":
            artifact = await mark_artifact_failed(db, artifact, error_message=error)
        return artifact


def _export_and_validate(
    record: Any,
    *,
    case: ArtifactCase,
    repeat: int,
    experiment_id: str,
) -> ValidationResult:
    from app.services.artifact_service import materialize_artifact_file

    export_dir = ARTIFACT_EXPORT_ROOT / experiment_id / case.case_id / f"repeat-{repeat}"
    export_dir.mkdir(parents=True, exist_ok=True)
    suffix = str(record.extension or Path(record.original_name).suffix)
    destination = export_dir / f"{record.artifact_type}{suffix}"
    with materialize_artifact_file(record) as source:
        shutil.copy2(source, destination)
    return validate_artifact(
        destination,
        artifact_type=record.artifact_type,
        required_term_groups=case.required_term_groups,
        backend_root=BACKEND_ROOT,
    )


async def run_batch(
    runtime: Any,
    *,
    sink: MemorySink,
    experiment_id: str,
    case: ArtifactCase,
    repeat: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from app.core.agent import get_thread_config
    from app.core.observability import RunContext

    user_id, plan_id, thread_id = await _ensure_benchmark_entities(
        experiment_id=experiment_id,
        case=case,
        repeat=repeat,
    )
    state = build_state(case, plan_id=plan_id, repeat=repeat)
    run_id = f"{experiment_id}-{case.case_id}-r{repeat}"
    context = RunContext(run_id=run_id, thread_id=thread_id, plan_id=plan_id, user_id=str(user_id))
    config = get_thread_config(
        thread_id,
        run_id=run_id,
        user_id=str(user_id),
        plan_id=plan_id,
        run_context=context,
        observation_sink=sink,
    )
    jobs = {
        "ppt": runtime.ppt_generate_node(state, config),
        "docx": runtime.docx_generate_node(state, config),
        "html-game": runtime.html_game_generate_node(state, config),
    }
    batch_started = time.perf_counter()

    async def execute(artifact_type: ArtifactType, awaitable: Any) -> tuple[ArtifactType, Any, str | None]:
        try:
            return artifact_type, await asyncio.wait_for(awaitable, timeout=timeout_seconds), None
        except TimeoutError:
            return artifact_type, None, f"Timed out after {timeout_seconds} seconds"
        except Exception as exc:
            return artifact_type, None, _safe_error(exc)

    outcomes = await asyncio.gather(*(execute(artifact_type, awaitable) for artifact_type, awaitable in jobs.items()))
    records: list[dict[str, Any]] = []
    for artifact_type, result, outer_error in outcomes:
        sub_run_id = f"{run_id}-{artifact_type}"
        payload = (result or {}).get(STATE_KEYS[artifact_type], {}) if isinstance(result, dict) else {}
        status = str(payload.get("status") or "failed")
        artifact_id = payload.get("artifact_id")
        error = outer_error or _safe_error(payload.get("error"))
        validation: dict[str, Any] | None = None
        size_bytes = 0
        storage_backend = None
        artifact_record = None
        if artifact_id is not None:
            artifact_record = await _load_artifact_record(int(artifact_id), user_id)
        elif outer_error:
            artifact_record = await _recover_failed_artifact_record(
                thread_id=thread_id,
                artifact_type=artifact_type,
                user_id=user_id,
                error=outer_error,
            )
            if artifact_record is not None:
                artifact_id = artifact_record.id
                status = artifact_record.status

        if artifact_record is not None:
            size_bytes = int(artifact_record.size_bytes or 0)
            storage_backend = artifact_record.storage_backend
            if status == "ready":
                try:
                    validation = _export_and_validate(
                        artifact_record,
                        case=case,
                        repeat=repeat,
                        experiment_id=experiment_id,
                    ).to_dict()
                except Exception as exc:
                    validation = ValidationResult(
                        artifact_type=artifact_type,
                        technical_pass=False,
                        quality_pass=False,
                        quality_score=0,
                        content_recall_pct=0,
                        errors=[_safe_error(exc) or exc.__class__.__name__],
                    ).to_dict()
        metrics = _observation_metrics(sink.events, sub_run_id)
        if metrics["duration_ms"] is None:
            metrics["duration_ms"] = round((time.perf_counter() - batch_started) * 1000)
        records.append(
            {
                "case_id": case.case_id,
                "repeat": repeat,
                "artifact_type": artifact_type,
                "status": status,
                "artifact_id": artifact_id,
                "size_bytes": size_bytes,
                "storage_backend": storage_backend,
                "failure_category": classify_failure(error),
                "error": error,
                "metrics": metrics,
                "validation": validation,
            }
        )
        print(
            f"[{case.case_id} r{repeat}] {artifact_type}: status={status}, "
            f"duration_ms={metrics['duration_ms']}, valid={bool(validation and validation['technical_pass'])}, "
            f"quality={bool(validation and validation['quality_pass'])}",
            flush=True,
        )
    batch = {
        "case_id": case.case_id,
        "repeat": repeat,
        "duration_ms": round((time.perf_counter() - batch_started) * 1000),
        "all_ready": all(record["status"] == "ready" for record in records),
        "all_technical_valid": all(
            bool(record["validation"] and record["validation"]["technical_pass"]) for record in records
        ),
    }
    return records, batch


async def run_preflight() -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.storage import build_storage_key, get_storage_service
    from app.core.workspace import WorkspaceManager
    from app.dependencies.db import async_engine, init_db

    checks: dict[str, bool] = {}
    details: dict[str, str] = {}
    await init_db()
    async with async_engine.connect() as connection:
        checks["database"] = (await connection.execute(text("select 1"))).scalar_one() == 1

    storage = get_storage_service()
    key = build_storage_key("benchmarks", "preflight", f"{int(time.time())}.txt")
    try:
        stored = storage.put_bytes(
            key=key,
            data=b"smartclass-artifact-benchmark",
            filename="preflight.txt",
            mime_type="text/plain",
        )
        checks["storage_round_trip"] = storage.read_bytes(
            storage_backend=stored.backend,
            storage_key=stored.key,
            storage_path=stored.storage_path,
        ) == b"smartclass-artifact-benchmark"
        details["storage_backend"] = stored.backend
    finally:
        try:
            storage.delete(storage_backend=storage.backend_type, storage_key=key, storage_path=None)
        except Exception:
            pass

    manager = WorkspaceManager()
    config = {"configurable": {"thread_id": "artifact-benchmark-preflight", "run_id": "node-modules"}}
    manager.write_file(
        config,
        relative_path="check_artifact_modules.js",
        content="for (const m of ['pptxgenjs','docx']) console.log(require.resolve(m));",
        overwrite=True,
    )
    execution = manager.run_code(config, language="node", entrypoint="check_artifact_modules.js")
    checks["node_dependencies"] = execution.exit_code == 0 and not execution.timed_out
    checks["office_validator"] = (
        BACKEND_ROOT / "skills" / "docx" / "scripts" / "office" / "validate.py"
    ).is_file()
    if not all(checks.values()):
        raise RuntimeError(f"Artifact benchmark preflight failed: {checks}")
    return {"checks": checks, "details": details}


def aggregate_report(report: dict[str, Any], *, expected_attempts: int) -> dict[str, Any]:
    attempts = report.get("attempts", [])
    batches = report.get("batches", [])

    def aggregate_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        ready = sum(row["status"] == "ready" for row in rows)
        validations = [row["validation"] for row in rows if row.get("validation")]
        technical = sum(bool(value["technical_pass"]) for value in validations)
        quality = sum(bool(value["quality_pass"]) for value in validations)
        durations = [float(row["metrics"]["duration_ms"]) for row in rows if row["metrics"].get("duration_ms")]
        scores = [float(value["quality_score"]) for value in validations]
        return {
            "attempts": total,
            "ready": ready,
            "pipeline_ready_rate_pct": _percent(ready, total),
            "technical_valid": technical,
            "technical_valid_rate_pct": _percent(technical, total),
            "quality_passed": quality,
            "usable_artifact_rate_pct": _percent(quality, total),
            "quality_score_mean": round(statistics.fmean(scores), 2) if scores else 0.0,
            "duration_ms_p50": _percentile(durations, 0.50),
            "duration_ms_p95": _percentile(durations, 0.95),
            "duration_ms_max": round(max(durations), 2) if durations else 0.0,
            "llm_calls": sum(int(row["metrics"].get("llm_call_count", 0)) for row in rows),
            "input_tokens": sum(int(row["metrics"].get("input_tokens", 0)) for row in rows),
            "output_tokens": sum(int(row["metrics"].get("output_tokens", 0)) for row in rows),
            "total_tokens": sum(int(row["metrics"].get("total_tokens", 0)) for row in rows),
            "tool_calls": sum(int(row["metrics"].get("tool_call_count", 0)) for row in rows),
            "workspace_executions": sum(
                int(row["metrics"].get("workspace_execution_count", 0)) for row in rows
            ),
        }

    overall = aggregate_rows(attempts)
    by_type = {
        artifact_type: aggregate_rows([row for row in attempts if row["artifact_type"] == artifact_type])
        for artifact_type in ARTIFACT_TYPES
    }
    failure_categories: dict[str, int] = {}
    for row in attempts:
        category = row.get("failure_category")
        if category:
            failure_categories[category] = failure_categories.get(category, 0) + 1
    evidence_gate = {
        "sample_complete": len(attempts) == expected_attempts,
        "all_ready_outputs_validated": all(
            row.get("validation") is not None for row in attempts if row["status"] == "ready"
        ),
        "all_failures_classified": all(
            row.get("failure_category") not in (None, "unknown") for row in attempts if row["status"] != "ready"
        ),
        "batch_count_complete": len(batches) == expected_attempts // len(ARTIFACT_TYPES),
    }
    product_targets = {
        "pipeline_ready_rate_at_least_90pct": overall["pipeline_ready_rate_pct"] >= 90,
        "technical_valid_rate_at_least_90pct": overall["technical_valid_rate_pct"] >= 90,
        "usable_artifact_rate_at_least_80pct": overall["usable_artifact_rate_pct"] >= 80,
    }
    return {
        "overall": overall,
        "by_type": by_type,
        "batch": {
            "batches": len(batches),
            "all_ready_rate_pct": _percent(sum(batch["all_ready"] for batch in batches), len(batches)),
            "all_technical_valid_rate_pct": _percent(
                sum(batch["all_technical_valid"] for batch in batches), len(batches)
            ),
            "duration_ms_p50": _percentile([batch["duration_ms"] for batch in batches], 0.50),
            "duration_ms_p95": _percentile([batch["duration_ms"] for batch in batches], 0.95),
        },
        "failure_categories": failure_categories,
        "evidence_gate": evidence_gate,
        "evidence_gate_passed": all(evidence_gate.values()),
        "product_targets": product_targets,
        "product_targets_met": all(product_targets.values()),
    }


def _provider_name(base_url: str | None) -> str:
    hostname = (urlparse(base_url or "").hostname or "").casefold()
    if "dashscope" in hostname:
        return "dashscope"
    if "openrouter" in hostname:
        return "openrouter"
    if "openai" in hostname:
        return "openai"
    return "openai-compatible"


def write_raw_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _git_metadata() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BACKEND_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
    )
    return commit, dirty


def _source_fingerprint() -> str:
    paths = [
        BACKEND_ROOT / "app" / "core" / "agent.py",
        BACKEND_ROOT / "app" / "services" / "artifact_service.py",
        BACKEND_ROOT / "skills" / "ppt-generator" / "SKILL.md",
        BACKEND_ROOT / "skills" / "docx" / "SKILL.md",
        BACKEND_ROOT / "skills" / "html-interactive" / "SKILL.md",
        CASES_PATH,
        Path(__file__).resolve(),
        Path(__file__).with_name("artifact_validation.py"),
    ]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(BACKEND_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def promote_baseline(report: dict[str, Any], *, baseline_id: str, command: str) -> Path:
    aggregate = report["aggregate"]
    if report["phase"] != "formal":
        raise RuntimeError("Only formal artifact experiments may be promoted")
    if not aggregate["evidence_gate_passed"]:
        raise RuntimeError("Artifact evidence gate failed; refusing to promote baseline")
    target = BASELINES_ROOT / baseline_id
    if target.exists():
        raise FileExistsError(f"Baseline already exists: {target}")
    target.mkdir(parents=True)
    public_summary = {
        key: report[key]
        for key in (
            "schema_version",
            "benchmark",
            "phase",
            "started_at",
            "duration_seconds",
            "sample_definition",
            "model",
            "runtime",
            "preflight",
            "aggregate",
        )
    }
    (target / "summary.json").write_text(
        json.dumps(public_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    commit, dirty = _git_metadata()
    manifest = {
        "baseline_id": baseline_id,
        "schema_version": SCHEMA_VERSION,
        "benchmark": report["benchmark"],
        "run_mode": "live-model-artifact-generation",
        "git_commit": commit,
        "repository_dirty": dirty,
        "source_fingerprint": _source_fingerprint(),
        "dataset_fingerprint": report["sample_definition"]["dataset_fingerprint"],
        "commands": [command],
        "sample_size": report["sample_definition"],
        "metric_definitions": {
            "pipeline_ready_rate_pct": "database ready artifacts / attempted artifacts",
            "technical_valid_rate_pct": "artifacts passing format, parser and schema validation / attempts",
            "usable_artifact_rate_pct": "artifacts passing technical gate and deterministic quality rubric / attempts",
            "duration_ms_p95": "nearest-rank p95 of artifact.generate end-to-end duration",
        },
        "environment": {"os": platform.platform(), "python": platform.python_version()},
        "limitations": [
            "Synthetic five-case benchmark; it does not represent production traffic.",
            "OnlyOffice and LibreOffice visual rendering were unavailable and are excluded.",
            "PPTX and DOCX are validated through OOXML ZIP/XML/schema and parser checks, not visual overflow inspection.",
            "HTML JavaScript receives static syntax and interaction-structure checks, not a full browser automation pass.",
            "Quality scores are deterministic rubric scores and are not human ratings.",
        ],
    }
    (target / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    rows = []
    for artifact_type in ARTIFACT_TYPES:
        metrics = aggregate["by_type"][artifact_type]
        rows.append(
            f"| {artifact_type} | {metrics['attempts']} | {metrics['pipeline_ready_rate_pct']:.2f}% | "
            f"{metrics['technical_valid_rate_pct']:.2f}% | {metrics['usable_artifact_rate_pct']:.2f}% | "
            f"{metrics['duration_ms_p50'] / 1000:.2f}s | {metrics['duration_ms_p95'] / 1000:.2f}s |"
        )
    overall = aggregate["overall"]
    report_md = f"""# SmartClass 产物生成基线

- Baseline：`{baseline_id}`
- 样本：5 个固定教学场景 × 2 次重复 × 3 类产物 = 30 次生成
- 模型：`{report['model']['name']}`
- Workspace：`{report['runtime']['workspace_backend']}`
- Storage：`{report['runtime']['storage_backend']}`
- 实验完整性门禁：{'通过' if aggregate['evidence_gate_passed'] else '未通过'}
- 产品目标：{'达到' if aggregate['product_targets_met'] else '未达到'}

| 类型 | 尝试 | Ready 率 | 技术有效率 | 可用产物率 | 耗时 p50 | 耗时 p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

总体 Ready 率为 **{overall['pipeline_ready_rate_pct']:.2f}%**，技术有效率为
**{overall['technical_valid_rate_pct']:.2f}%**，可用产物率为 **{overall['usable_artifact_rate_pct']:.2f}%**；
单产物生成耗时 p50/p95 为 **{overall['duration_ms_p50'] / 1000:.2f}s / {overall['duration_ms_p95'] / 1000:.2f}s**。

## 限制

本轮 OnlyOffice/LibreOffice 不可用，因此未执行 Office 视觉渲染与溢出检查。PPTX/DOCX 使用
ZIP、XML、OOXML schema 和解析器校验；HTML 使用静态语法与交互结构校验。质量分是确定性 rubric，
不等同于人工视觉或教学专家评分。
"""
    (target / "report.md").write_text(report_md, encoding="utf-8")
    return target


async def run_experiment(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    from app.config import get_storage_backend, get_workspace_execution_backend
    from app.core.agent import AgentRuntime
    from app.core.llm import get_model
    from app.core.skills import create_skill_registry
    from app.dependencies.db import close_db_resources

    all_cases = load_cases()
    selected_cases = all_cases[: PHASE_CASE_COUNTS[args.phase]]
    repeats = args.repeats or PHASE_REPEATS[args.phase]
    expected_attempts = len(selected_cases) * repeats * len(ARTIFACT_TYPES)
    experiment_id = args.experiment_id or f"artifact-{args.phase}-{int(time.time())}"
    output = args.output or RAW_RESULTS_DIR / f"artifact_generation_{experiment_id}.json"
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    preflight = await run_preflight()
    model = get_model(streaming=False)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "artifact-generation",
        "phase": args.phase,
        "experiment_id": experiment_id,
        "started_at": started_at.isoformat(),
        "duration_seconds": 0.0,
        "sample_definition": {
            "case_count": len(selected_cases),
            "case_ids": [case.case_id for case in selected_cases],
            "repeats": repeats,
            "artifact_types": list(ARTIFACT_TYPES),
            "expected_attempts": expected_attempts,
            "dataset_fingerprint": cases_fingerprint(),
            "synthetic_inputs": True,
        },
        "model": {
            "name": str(getattr(model, "model_name", "unknown")),
            "provider": _provider_name(str(getattr(model, "openai_api_base", "") or "")),
        },
        "runtime": {
            "workspace_backend": get_workspace_execution_backend(),
            "storage_backend": get_storage_backend(),
            "artifact_timeout_seconds": args.timeout_seconds,
            "office_visual_validation": False,
        },
        "preflight": preflight,
        "attempts": [],
        "batches": [],
    }
    write_raw_report(report, output)
    runtime = AgentRuntime(
        checkpointer=None,
        memory_store=None,
        rag_runtime=None,
        skill_registry=create_skill_registry(),
        video_transcription_runtime=None,
    )
    sink = MemorySink()
    try:
        for repeat in range(1, repeats + 1):
            for case in selected_cases:
                print(f"[batch] case={case.case_id}, repeat={repeat}", flush=True)
                attempts, batch = await run_batch(
                    runtime,
                    sink=sink,
                    experiment_id=experiment_id,
                    case=case,
                    repeat=repeat,
                    timeout_seconds=args.timeout_seconds,
                )
                report["attempts"].extend(attempts)
                report["batches"].append(batch)
                report["duration_seconds"] = round(time.perf_counter() - started, 2)
                report["aggregate"] = aggregate_report(report, expected_attempts=expected_attempts)
                write_raw_report(report, output)
    finally:
        report["duration_seconds"] = round(time.perf_counter() - started, 2)
        report["aggregate"] = aggregate_report(report, expected_attempts=expected_attempts)
        write_raw_report(report, output)
        await close_db_resources()
    return report, output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SmartClass live artifact-generation benchmark")
    parser.add_argument("--phase", choices=tuple(PHASE_CASE_COUNTS), default="smoke")
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--experiment-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--local-docker-services", action="store_true")
    parser.add_argument("--model-env", type=Path)
    parser.add_argument("--model-profile", choices=("main", "structured", "small"), default="main")
    parser.add_argument("--promote-baseline")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.repeats is not None and args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.local_docker_services:
        configure_local_docker_services(WORKSPACE_ROOT / ".env.docker")
    if args.model_env:
        configure_model_environment(args.model_env.resolve(), profile=args.model_profile)
    report, output = asyncio.run(run_experiment(args))
    print(f"Raw report: {output}")
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    if args.promote_baseline:
        command = (
            "python -m tests.benchmarks.artifact_generation "
            f"--phase {args.phase} --timeout-seconds {args.timeout_seconds} "
            "--local-docker-services "
            f"--model-env {args.model_env or '../.env.docker'} "
            f"--model-profile {args.model_profile} "
            f"--promote-baseline {args.promote_baseline}"
        )
        target = promote_baseline(report, baseline_id=args.promote_baseline, command=command)
        print(f"Promoted baseline: {target}")
    return 0 if report["aggregate"]["evidence_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
