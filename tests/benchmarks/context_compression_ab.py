from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage

from app.core.context_compression import (
    CompressionResult,
    CompressionSettings,
    build_compression_plan,
    build_compression_prompt,
    compress_state_messages,
    estimate_message_tokens,
    is_compressed_context_message,
    message_to_text,
)
from app.core.llm import get_context_compression_llm
from app.core.observability import ObservationEvent, RunContext

BENCHMARK_SCHEMA_VERSION = "1.0"
DEFAULT_TURNS = (30, 50, 100)
DEFAULT_REPEATS = 3
DEFAULT_TRIGGER_TOKENS = 6000
DEFAULT_KEEP_RECENT_TURNS = 6
DEFAULT_MAX_OUTPUT_TOKENS = 800
DEFAULT_MAX_PREFACE_CHARS = 6000

BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = BACKEND_ROOT.parent
RAW_RESULTS_DIR = BACKEND_ROOT / "tests" / "evals" / "results"
BASELINES_DIR = WORKSPACE_ROOT / "docs" / "benchmarks" / "baselines"

HISTORICAL_FACTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "opening_scenario": (("旗杆",), ("测高", "测量高度")),
    "privacy_constraint": (("学生姓名",), ("联系方式",)),
    "deliverables": (("PPT", "课件"), ("DOCX", "教案")),
    "open_question": (("投影仪", "投影设备"),),
}

STRUCTURED_FACTS: dict[str, tuple[str, ...]] = {
    "subject": ("数学",),
    "grade": ("八年级",),
    "topic": ("勾股定理",),
    "duration": ("45",),
    "artifact": ("勾股定理探究课件",),
}


class MemorySink:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def emit(self, event: ObservationEvent) -> None:
        self.events.append(event)


def _percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator * 100 / denominator, 2)


def _reduction_percent(after: float, before: float) -> float:
    if before <= 0:
        return 0.0
    return round((1 - after / before) * 100, 2)


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(float(ordered[rank]), 2)


def _normalize(text: str) -> str:
    return "".join(text.upper().split())


def _fact_is_present(text: str, alternatives: tuple[tuple[str, ...], ...]) -> bool:
    normalized = _normalize(text)
    return all(any(_normalize(term) in normalized for term in group) for group in alternatives)


def build_synthetic_state() -> dict[str, Any]:
    return {
        "messages": [],
        "teaching_metadata": {
            "subject": "数学",
            "grade": "八年级",
            "topic": "勾股定理",
            "duration_minutes": 45,
            "class_size": 42,
            "learning_objectives": [
                "理解勾股定理的条件与结论",
                "能用定理解决真实测量问题",
            ],
        },
        "teaching_design_plan": (
            "采用情境导入、分组探究、例题迁移和形成性评价四段式流程；"
            "每个活动都要标明教师行为、学生活动和评价证据。"
        ),
        "rag_context": "教材建议先通过面积拼图建立直观认识，再过渡到符号表达与实际测量。",
        "rag_results": [
            {
                "source": "synthetic-textbook",
                "section": "勾股定理",
                "digest": "直角三角形两直角边平方和等于斜边平方。",
            }
        ],
        "artifact_catalog": [
            {
                "id": "synthetic-ppt-1",
                "type": "ppt",
                "title": "勾股定理探究课件",
                "status": "ready",
            }
        ],
        "revision_targets": [],
        "revision_results": [],
    }


def _historical_instruction(turn: int) -> str:
    special = {
        1: "导入情境固定为校园旗杆测高，学生通过影长和直角三角形关系估算旗杆高度。",
        2: "隐私约束：课堂记录不得出现学生姓名或联系方式，只保留匿名小组编号。",
        3: "最终交付物必须同时包含 PPT 课件和 DOCX 教案，两者的活动顺序要保持一致。",
        4: "未决问题：教室是否配备投影仪，需要在最终生成前提醒教师确认。",
    }
    return special.get(turn, "本轮继续细化活动步骤、时间分配、教师追问与形成性评价证据。")


def build_turn_messages(turn: int) -> tuple[HumanMessage, AIMessage]:
    instruction = _historical_instruction(turn)
    human_detail = (
        f"这是第 {turn} 轮备课讨论。{instruction}"
        "请结合八年级学生的认知水平，把任务拆成可执行步骤，并说明如何观察学生是否真正理解。"
        "活动应兼顾基础学生和学有余力学生，不要改变已经确认的教学主题与课时长度。"
        "请同步检查本轮建议是否与教材摘要、既有课件状态以及前面确认的限制冲突。"
    )
    human_content = "\n".join([human_detail, human_detail, f"本轮校验编号：TURN-{turn:03d}。"])

    assistant_detail = (
        f"第 {turn} 轮建议采用“问题呈现—独立思考—小组论证—全班交流—即时检测”的闭环。"
        "教师先明确任务产出和成功标准，再用递进问题暴露学生对直角边、斜边及适用条件的理解。"
        "学生需要写出推理依据、比较两种解法并用一句话解释结论，教师以观察表记录匿名小组的证据。"
        "对基础学生提供图形标注与句式支架，对进阶学生增加逆向判断或真实测量误差分析。"
        "形成性评价包含口头追问、白板展示和一分钟退出条，若多数学生混淆斜边则回到图形辨识环节。"
        "本轮设计继续服从已确认的学科、年级、主题、课时、资源及产物约束，不替代尚待教师确认的事项。"
    )
    assistant_content = "\n".join(
        [
            assistant_detail,
            assistant_detail,
            assistant_detail,
            f"已完成第 {turn} 轮校验，追踪编号：REPLY-{turn:03d}。",
        ]
    )
    return (
        HumanMessage(id=f"h-{turn:03d}", content=human_content),
        AIMessage(id=f"a-{turn:03d}", content=assistant_content),
    )


def apply_compression_result(state: dict[str, Any], result: CompressionResult) -> None:
    if result.status != "success" or not result.update:
        return
    state["messages"] = [
        message for message in result.update["messages"] if isinstance(message, BaseMessage) and not isinstance(message, RemoveMessage)
    ]


def _context_text(messages: Iterable[BaseMessage]) -> str:
    return "\n".join(message_to_text(message) for message in messages)


def _retention_metrics(state: dict[str, Any], *, total_turns: int, keep_recent_turns: int) -> dict[str, Any]:
    messages = [message for message in state.get("messages", []) if isinstance(message, BaseMessage)]
    context_text = _context_text(messages)
    historical_hits = {
        fact: _fact_is_present(context_text, alternatives) for fact, alternatives in HISTORICAL_FACTS.items()
    }
    structured_hits = {
        fact: all(_normalize(term) in _normalize(context_text) for term in terms)
        for fact, terms in STRUCTURED_FACTS.items()
    }

    by_id = {str(message.id): message_to_text(message) for message in messages if getattr(message, "id", None)}
    recent_start = max(1, total_turns - keep_recent_turns + 1)
    recent_checks: list[bool] = []
    for turn in range(recent_start, total_turns + 1):
        expected_human, expected_ai = build_turn_messages(turn)
        recent_checks.extend(
            [
                by_id.get(str(expected_human.id)) == message_to_text(expected_human),
                by_id.get(str(expected_ai.id)) == message_to_text(expected_ai),
            ]
        )

    return {
        "historical_fact_hits": historical_hits,
        "historical_fact_recall_pct": _percent(sum(historical_hits.values()), len(historical_hits)),
        "structured_fact_hits": structured_hits,
        "structured_fact_recall_pct": _percent(sum(structured_hits.values()), len(structured_hits)),
        "recent_message_exact_match_pct": _percent(sum(recent_checks), len(recent_checks)),
        "compressed_context_present": any(is_compressed_context_message(message) for message in messages),
    }


def _authoritative_state_digest(state: dict[str, Any]) -> str:
    payload = {key: value for key, value in state.items() if key != "messages"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _message_digest(state: dict[str, Any]) -> str:
    payload = [
        {
            "id": str(getattr(message, "id", "") or ""),
            "type": message.__class__.__name__,
            "content": message_to_text(message),
        }
        for message in state.get("messages", [])
        if isinstance(message, BaseMessage)
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _llm_usage_since(events: Sequence[ObservationEvent], start: int) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for event in events[start:]:
        if event.event != "llm.call" or event.status != "success":
            continue
        for key in totals:
            value = event.fields.get(key)
            if isinstance(value, int):
                totals[key] += value
    return totals


def _snapshot(
    state: dict[str, Any],
    *,
    turns: int,
    cumulative_prompt_tokens: int,
    compression_attempts: Sequence[dict[str, Any]],
    settings: CompressionSettings,
    authoritative_digest: str,
) -> dict[str, Any]:
    messages = [message for message in state.get("messages", []) if isinstance(message, BaseMessage)]
    attempts = [attempt for attempt in compression_attempts if attempt["turn"] <= turns]
    successful = [attempt for attempt in attempts if attempt["status"] == "success"]
    failed = [attempt for attempt in attempts if attempt["status"] == "failed"]
    usage = {
        key: sum(int(attempt["provider_usage"].get(key, 0)) for attempt in attempts)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    estimated_overhead = sum(int(attempt["estimated_overhead_tokens"]) for attempt in attempts)
    return {
        "turns": turns,
        "cumulative_prompt_tokens": cumulative_prompt_tokens,
        "final_context_tokens": estimate_message_tokens(messages),
        "final_message_count": len(messages),
        "compression_attempts": len(attempts),
        "compression_calls": len(successful),
        "failed_compressions": len(failed),
        "compression_attempt_latency_ms": [int(attempt["duration_ms"]) for attempt in attempts],
        "failure_fallback_preserved_pct": _percent(
            sum(bool(attempt["fallback_preserved"]) for attempt in failed),
            len(failed),
        )
        if failed
        else 100.0,
        "compression_estimated_overhead_tokens": estimated_overhead,
        "compression_provider_usage": usage,
        "authoritative_state_unchanged": _authoritative_state_digest(state) == authoritative_digest,
        "retention": _retention_metrics(
            state,
            total_turns=turns,
            keep_recent_turns=settings.keep_recent_turns,
        ),
    }


async def run_control(
    *,
    max_turns: int,
    checkpoints: set[int],
    settings: CompressionSettings,
) -> dict[int, dict[str, Any]]:
    state = build_synthetic_state()
    authoritative_digest = _authoritative_state_digest(state)
    off_settings = CompressionSettings(
        enabled=False,
        trigger_tokens=settings.trigger_tokens,
        keep_recent_turns=settings.keep_recent_turns,
        max_output_tokens=settings.max_output_tokens,
        max_preface_chars=settings.max_preface_chars,
    )
    cumulative_prompt_tokens = 0
    snapshots: dict[int, dict[str, Any]] = {}
    for turn in range(1, max_turns + 1):
        human, assistant = build_turn_messages(turn)
        state["messages"].append(human)
        cumulative_prompt_tokens += estimate_message_tokens(state["messages"])
        state["messages"].append(assistant)
        result = await compress_state_messages(
            state,
            context=RunContext(run_id=f"compression-ab-control-{turn}", thread_id="synthetic-control"),
            sink=MemorySink(),
            settings=off_settings,
        )
        if result.status != "skipped" or result.reason != "disabled":
            raise RuntimeError(f"Control arm unexpectedly changed context at turn {turn}: {result}")
        if turn in checkpoints:
            snapshots[turn] = _snapshot(
                state,
                turns=turn,
                cumulative_prompt_tokens=cumulative_prompt_tokens,
                compression_attempts=[],
                settings=settings,
                authoritative_digest=authoritative_digest,
            )
    return snapshots


async def run_treatment(
    *,
    repeat: int,
    max_turns: int,
    checkpoints: set[int],
    settings: CompressionSettings,
    model: Any,
) -> dict[int, dict[str, Any]]:
    state = build_synthetic_state()
    authoritative_digest = _authoritative_state_digest(state)
    cumulative_prompt_tokens = 0
    compression_attempts: list[dict[str, Any]] = []
    snapshots: dict[int, dict[str, Any]] = {}
    sink = MemorySink()

    for turn in range(1, max_turns + 1):
        human, assistant = build_turn_messages(turn)
        state["messages"].append(human)
        cumulative_prompt_tokens += estimate_message_tokens(state["messages"])
        state["messages"].append(assistant)

        plan = build_compression_plan(state, settings=settings)
        estimated_input = 0
        if plan.should_compress:
            estimated_input = estimate_message_tokens(build_compression_prompt(state, plan, settings=settings))
        event_start = len(sink.events)
        messages_before_attempt = _message_digest(state)
        result = await compress_state_messages(
            state,
            context=RunContext(
                run_id=f"compression-ab-treatment-{repeat}-{turn}",
                thread_id=f"synthetic-treatment-{repeat}",
            ),
            sink=sink,
            settings=settings,
            model=model,
        )
        if result.status == "success":
            provider_usage = _llm_usage_since(sink.events, event_start)
            estimated_output = max(1, (result.summary_size + 3) // 4)
            compression_attempts.append(
                {
                    "turn": turn,
                    "status": "success",
                    "duration_ms": result.duration_ms,
                    "estimated_input_tokens": estimated_input,
                    "estimated_output_tokens": estimated_output,
                    "estimated_overhead_tokens": estimated_input + estimated_output,
                    "provider_usage": provider_usage,
                    "fallback_preserved": None,
                }
            )
            apply_compression_result(state, result)
            print(
                f"[treatment {repeat}] compressed at turn {turn}: "
                f"{result.estimated_tokens_before} -> {result.estimated_tokens_after} estimated tokens, "
                f"{result.duration_ms} ms",
                flush=True,
            )
        elif result.status == "failed":
            compression_attempts.append(
                {
                    "turn": turn,
                    "status": "failed",
                    "duration_ms": result.duration_ms,
                    "estimated_input_tokens": estimated_input,
                    "estimated_output_tokens": 0,
                    "estimated_overhead_tokens": estimated_input,
                    "provider_usage": _llm_usage_since(sink.events, event_start),
                    "fallback_preserved": _message_digest(state) == messages_before_attempt,
                }
            )
            print(
                f"[treatment {repeat}] compression failed at turn {turn}: {result.reason}",
                flush=True,
            )

        if turn in checkpoints:
            snapshots[turn] = _snapshot(
                state,
                turns=turn,
                cumulative_prompt_tokens=cumulative_prompt_tokens,
                compression_attempts=compression_attempts,
                settings=settings,
                authoritative_digest=authoritative_digest,
            )
    return snapshots


def aggregate_report(
    *,
    controls: dict[int, dict[str, Any]],
    treatments: Sequence[dict[int, dict[str, Any]]],
    settings: CompressionSettings,
    model_name: str,
    started_at: datetime,
    duration_seconds: float,
) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    max_turns = max(controls)
    final_rows = [replicate[max_turns] for replicate in treatments]
    all_latencies = [
        latency for row in final_rows for latency in row["compression_attempt_latency_ms"]
    ]
    total_failures = sum(int(row["failed_compressions"]) for row in final_rows)

    for turns in sorted(controls):
        control = controls[turns]
        treatment_rows = [replicate[turns] for replicate in treatments]
        prompt_values = [row["cumulative_prompt_tokens"] for row in treatment_rows]
        context_values = [row["final_context_tokens"] for row in treatment_rows]
        overhead_values = [row["compression_estimated_overhead_tokens"] for row in treatment_rows]
        net_values = [prompt + overhead for prompt, overhead in zip(prompt_values, overhead_values, strict=True)]
        latencies = [latency for row in treatment_rows for latency in row["compression_attempt_latency_ms"]]
        attempts = sum(int(row["compression_attempts"]) for row in treatment_rows)
        successful_calls = sum(int(row["compression_calls"]) for row in treatment_rows)
        failures = sum(int(row["failed_compressions"]) for row in treatment_rows)
        scenarios.append(
            {
                "turns": turns,
                "repeats": len(treatment_rows),
                "control": {
                    "cumulative_prompt_tokens": control["cumulative_prompt_tokens"],
                    "final_context_tokens": control["final_context_tokens"],
                    "final_message_count": control["final_message_count"],
                },
                "treatment": {
                    "cumulative_prompt_tokens_mean": round(statistics.fmean(prompt_values), 2),
                    "final_context_tokens_mean": round(statistics.fmean(context_values), 2),
                    "final_message_count_mean": round(
                        statistics.fmean(row["final_message_count"] for row in treatment_rows),
                        2,
                    ),
                    "compression_attempts_total": attempts,
                    "compression_calls_total": successful_calls,
                    "compression_calls_mean": round(
                        statistics.fmean(row["compression_calls"] for row in treatment_rows),
                        2,
                    ),
                    "compression_failures": failures,
                    "compression_attempt_success_rate_pct": _percent(successful_calls, attempts),
                    "failure_fallback_preserved_pct": round(
                        statistics.fmean(row["failure_fallback_preserved_pct"] for row in treatment_rows),
                        2,
                    ),
                    "compression_estimated_overhead_tokens_mean": round(statistics.fmean(overhead_values), 2),
                    "compression_latency_ms_p50": _percentile(latencies, 0.50),
                    "compression_latency_ms_p95": _percentile(latencies, 0.95),
                    "historical_fact_recall_pct": round(
                        statistics.fmean(
                            row["retention"]["historical_fact_recall_pct"] for row in treatment_rows
                        ),
                        2,
                    ),
                    "structured_fact_recall_pct": round(
                        statistics.fmean(
                            row["retention"]["structured_fact_recall_pct"] for row in treatment_rows
                        ),
                        2,
                    ),
                    "recent_message_exact_match_pct": round(
                        statistics.fmean(
                            row["retention"]["recent_message_exact_match_pct"] for row in treatment_rows
                        ),
                        2,
                    ),
                    "authoritative_state_unchanged_pct": _percent(
                        sum(bool(row["authoritative_state_unchanged"]) for row in treatment_rows),
                        len(treatment_rows),
                    ),
                },
                "comparison": {
                    "main_prompt_token_reduction_pct": _reduction_percent(
                        statistics.fmean(prompt_values),
                        control["cumulative_prompt_tokens"],
                    ),
                    "net_estimated_token_reduction_pct": _reduction_percent(
                        statistics.fmean(net_values),
                        control["cumulative_prompt_tokens"],
                    ),
                    "final_context_token_reduction_pct": _reduction_percent(
                        statistics.fmean(context_values),
                        control["final_context_tokens"],
                    ),
                },
            }
        )

    quality_gate = {
        "compression_attempt_success_rate_at_least_90pct": all(
            scenario["treatment"]["compression_attempt_success_rate_pct"] >= 90 for scenario in scenarios
        ),
        "failure_fallback_preserved_100pct": all(
            scenario["treatment"]["failure_fallback_preserved_pct"] == 100 for scenario in scenarios
        ),
        "authoritative_state_unchanged_100pct": all(
            scenario["treatment"]["authoritative_state_unchanged_pct"] == 100 for scenario in scenarios
        ),
        "structured_fact_recall_100pct": all(
            scenario["treatment"]["structured_fact_recall_pct"] == 100 for scenario in scenarios
        ),
        "recent_message_exact_match_100pct": all(
            scenario["treatment"]["recent_message_exact_match_pct"] == 100 for scenario in scenarios
        ),
        "historical_fact_recall_at_least_90pct": all(
            scenario["treatment"]["historical_fact_recall_pct"] >= 90 for scenario in scenarios
        ),
        "net_reduction_positive_at_50_and_100_turns": all(
            scenario["comparison"]["net_estimated_token_reduction_pct"] > 0
            for scenario in scenarios
            if scenario["turns"] in {50, 100}
        ),
    }
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "benchmark": "context-compression-ab",
        "started_at": started_at.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "run_mode": "live-model-ab",
        "sample_definition": {
            "turn_checkpoints": sorted(controls),
            "treatment_repeats": len(treatments),
            "synthetic_conversation": True,
            "main_agent_responses": "deterministic fixtures",
        },
        "settings": asdict(settings),
        "model": {"name": model_name, "provider": "dashscope"},
        "token_measurement": {
            "main_prompt": "production estimate_message_tokens fallback (characters / 4)",
            "compression_overhead": "same estimator for prompt and compressed-message size",
            "provider_usage_recorded_locally": True,
        },
        "scenarios": scenarios,
        "latency_overall": {
            "compression_attempts": len(all_latencies),
            "compression_failures": total_failures,
            "p50_ms": _percentile(all_latencies, 0.50),
            "p95_ms": _percentile(all_latencies, 0.95),
            "max_ms": round(max(all_latencies), 2) if all_latencies else 0.0,
        },
        "quality_gate": quality_gate,
        "quality_gate_passed": all(quality_gate.values()),
        "replicates": [
            {
                "repeat": index,
                "snapshots": [replicate[turns] for turns in sorted(replicate)],
            }
            for index, replicate in enumerate(treatments, start=1)
        ],
    }


def _git_metadata() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BACKEND_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


def _source_fingerprint() -> str:
    paths = [
        BACKEND_ROOT / "app" / "core" / "context_compression.py",
        BACKEND_ROOT / "app" / "core" / "agent.py",
        Path(__file__).resolve(),
    ]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(BACKEND_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def write_raw_report(report: dict[str, Any], output: Path | None = None) -> Path:
    RAW_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = output or RAW_RESULTS_DIR / f"context_compression_ab_{int(time.time())}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def promote_baseline(
    report: dict[str, Any],
    *,
    baseline_id: str,
    command: str,
    replace: bool = False,
) -> Path:
    if not report.get("quality_gate_passed"):
        raise RuntimeError("Benchmark quality gate failed; refusing to promote baseline.")
    target = BASELINES_DIR / baseline_id
    if target.exists() and not replace:
        raise FileExistsError(f"Baseline already exists: {target}")
    target.mkdir(parents=True, exist_ok=replace)

    commit, dirty = _git_metadata()
    public_summary = {
        "schema_version": report["schema_version"],
        "benchmark": report["benchmark"],
        "run_mode": report["run_mode"],
        "duration_seconds": report["duration_seconds"],
        "sample_definition": report["sample_definition"],
        "settings": report["settings"],
        "model": report["model"],
        "token_measurement": report["token_measurement"],
        "scenarios": report["scenarios"],
        "latency_overall": report["latency_overall"],
        "quality_gate": report["quality_gate"],
        "quality_gate_passed": report["quality_gate_passed"],
    }
    (target / "summary.json").write_text(
        json.dumps(public_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "baseline_id": baseline_id,
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "benchmark": report["benchmark"],
        "run_mode": report["run_mode"],
        "git_commit": commit,
        "repository_dirty": dirty,
        "source_fingerprint": _source_fingerprint(),
        "commands": [command],
        "sample_size": {
            "turn_checkpoints": report["sample_definition"]["turn_checkpoints"],
            "treatment_repeats": report["sample_definition"]["treatment_repeats"],
        },
        "metric_definitions": {
            "main_prompt_token_reduction_pct": "1 - treatment cumulative prompt estimate / control",
            "net_estimated_token_reduction_pct": (
                "1 - (treatment cumulative prompt estimate + compression estimated overhead) / control"
            ),
            "compression_latency_ms_p95": "nearest-rank p95 of all live compression attempts, including failures",
            "fact_recall_pct": "matched predefined synthetic fact groups / expected fact groups",
            "failure_fallback_preserved_pct": "failed attempts that left the complete message state unchanged / failures",
        },
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "limitations": [
            "Synthetic long-thread benchmark; it does not represent production traffic.",
            "Main prompt and compression overhead tokens use the production characters/4 fallback because the Qwen tokenizer is unavailable locally.",
            "Main Agent responses are deterministic fixtures; only context summaries invoke the live model.",
            "Latency includes the configured remote model endpoint, timeout attempts, and local orchestration.",
        ],
        "replaced_existing_baseline": replace,
    }
    try:
        import yaml

        manifest_text = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
    except ImportError:
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    (target / "manifest.yaml").write_text(manifest_text, encoding="utf-8")

    rows = []
    for scenario in report["scenarios"]:
        treatment = scenario["treatment"]
        comparison = scenario["comparison"]
        rows.append(
            "| {turns} | {control:,} | {treatment:,.0f} | {main:.2f}% | {net:.2f}% | "
            "{p95:,.0f} ms | {history:.1f}% | {recent:.1f}% |".format(
                turns=scenario["turns"],
                control=scenario["control"]["cumulative_prompt_tokens"],
                treatment=treatment["cumulative_prompt_tokens_mean"],
                main=comparison["main_prompt_token_reduction_pct"],
                net=comparison["net_estimated_token_reduction_pct"],
                p95=treatment["compression_latency_ms_p95"],
                history=treatment["historical_fact_recall_pct"],
                recent=treatment["recent_message_exact_match_pct"],
            )
        )
    report_md = f"""# SmartClass 上下文压缩 A/B 基线

- Baseline：`{baseline_id}`
- 场景：固定合成长对话，A 组关闭压缩，B 组开启生产压缩入口
- 模型：`{report["model"]["name"]}`（仅 B 组摘要调用）
- 配置：阈值 {report["settings"]["trigger_tokens"]}，保留近期 {report["settings"]["keep_recent_turns"]} 轮
- 重复次数：B 组 {report["sample_definition"]["treatment_repeats"]} 次
- 压缩尝试：{report["latency_overall"]["compression_attempts"]} 次，失败 {report["latency_overall"]["compression_failures"]} 次
- 压缩尝试延迟：p50 {report["latency_overall"]["p50_ms"] / 1000:.2f}s，p95 {report["latency_overall"]["p95_ms"] / 1000:.2f}s
- 质量门禁：{"通过" if report["quality_gate_passed"] else "未通过"}

| 对话轮数 | A 累计 Prompt 估算 | B 累计 Prompt 估算 | 主链路削减 | 含压缩开销净削减 | 压缩延迟 p95 | 历史事实保留 | 近期消息精确保留 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## 口径与限制

Token 采用当前生产 `estimate_message_tokens` 的字符数/4回退口径，因为 Qwen 模型未提供本地 tokenizer。
“含压缩开销净削减”把压缩 Prompt 与摘要大小按同一口径计入。该实验使用固定的合成教师备课对话，
主 Agent 回复为确定性 fixture，只有上下文摘要调用真实模型；结果是可复现 benchmark，不代表生产流量。
"""
    (target / "report.md").write_text(report_md, encoding="utf-8")
    return target


async def run_benchmark(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    turns = tuple(sorted(set(args.turns)))
    if not turns or min(turns) <= 0:
        raise ValueError("--turns must contain positive integers")
    if args.repeats <= 0:
        raise ValueError("--repeats must be positive")

    settings = CompressionSettings(
        enabled=True,
        trigger_tokens=args.trigger_tokens,
        keep_recent_turns=args.keep_recent_turns,
        max_output_tokens=args.max_output_tokens,
        max_preface_chars=args.max_preface_chars,
    )
    model = get_context_compression_llm(streaming=False)
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    checkpoints = set(turns)

    print(f"[control] running through {max(turns)} turns", flush=True)
    control = await run_control(max_turns=max(turns), checkpoints=checkpoints, settings=settings)
    treatments = []
    for repeat in range(1, args.repeats + 1):
        print(f"[treatment {repeat}] running through {max(turns)} turns", flush=True)
        treatments.append(
            await run_treatment(
                repeat=repeat,
                max_turns=max(turns),
                checkpoints=checkpoints,
                settings=settings,
                model=model,
            )
        )

    report = aggregate_report(
        controls=control,
        treatments=treatments,
        settings=settings,
        model_name=str(getattr(model, "model_name", "unknown")),
        started_at=started_at,
        duration_seconds=time.perf_counter() - started,
    )
    output = write_raw_report(report, args.output)
    return report, output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SmartClass context-compression A/B benchmark.")
    parser.add_argument("--turns", nargs="+", type=int, default=list(DEFAULT_TURNS))
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--trigger-tokens", type=int, default=DEFAULT_TRIGGER_TOKENS)
    parser.add_argument("--keep-recent-turns", type=int, default=DEFAULT_KEEP_RECENT_TURNS)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--max-preface-chars", type=int, default=DEFAULT_MAX_PREFACE_CHARS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--promote-baseline")
    parser.add_argument("--replace-baseline", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    report, output = asyncio.run(run_benchmark(args))
    print(f"Raw report: {output}")
    print(json.dumps({"quality_gate_passed": report["quality_gate_passed"], "scenarios": report["scenarios"]}, ensure_ascii=False, indent=2))
    if args.promote_baseline:
        command = (
            "python -m tests.benchmarks.context_compression_ab "
            f"--turns {' '.join(str(turn) for turn in args.turns)} "
            f"--repeats {args.repeats} --trigger-tokens {args.trigger_tokens} "
            f"--keep-recent-turns {args.keep_recent_turns} "
            f"--max-output-tokens {args.max_output_tokens} "
            f"--max-preface-chars {args.max_preface_chars} "
            f"--promote-baseline {args.promote_baseline}"
        )
        target = promote_baseline(
            report,
            baseline_id=args.promote_baseline,
            command=command,
            replace=args.replace_baseline,
        )
        print(f"Promoted baseline: {target}")
    return 0 if report["quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
