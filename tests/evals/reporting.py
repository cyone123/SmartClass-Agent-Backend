"""Promote raw evaluation reports into privacy-safe benchmark evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.observability import sanitize_observation_fields
from tests.evals.check_regression import check_regression, is_legacy_report, load_eval_result

BASELINE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class BaselinePromotionError(ValueError):
    pass


def default_benchmarks_root() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "benchmarks"


def _safe_category_metrics(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    allowed = ("count", "passed", "failed", "error", "pass_rate", "error_rate", "avg_score")
    return {
        str(category): {
            key: metrics[key]
            for key in allowed
            if isinstance(metrics, dict) and key in metrics
        }
        for category, metrics in value.items()
    }


def build_sanitized_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Return aggregate-only fields suitable for committing to the repository."""
    allowed_environment = report.get("environment") if isinstance(report.get("environment"), dict) else {}
    safe_environment = sanitize_observation_fields(allowed_environment)
    return {
        "schema_version": report.get("schema_version"),
        "suite_id": report.get("suite_id"),
        "run_mode": report.get("run_mode"),
        "total_cases": int(report.get("total_cases", 0)),
        "passed": int(report.get("passed", 0)),
        "failed": int(report.get("failed", 0)),
        "error": int(report.get("error", 0)),
        "pass_rate": float(report.get("pass_rate", 0.0)),
        "error_rate": float(report.get("error_rate", 0.0)),
        "avg_score": float(report.get("avg_score", 0.0)),
        "category_metrics": _safe_category_metrics(report.get("category_metrics")),
        "dataset_fingerprint": report.get("dataset_fingerprint", ""),
        "git_commit": report.get("git_commit", "unknown"),
        "model": {
            key: value
            for key, value in (report.get("model") or {}).items()
            if key in {"provider", "model", "temperature", "top_p", "max_tokens", "judge_model"}
        },
        "environment": safe_environment,
        "execution_time": float(report.get("execution_time", 0.0)),
        "timestamp": report.get("timestamp"),
    }


def build_manifest(
    report: dict[str, Any],
    *,
    baseline_id: str,
    source_report: Path,
    replaced: bool = False,
) -> dict[str, Any]:
    report_manifest = report.get("manifest") if isinstance(report.get("manifest"), dict) else {}
    return {
        "baseline_id": baseline_id,
        "schema_version": "1.0",
        "source_report_name": source_report.name,
        "run_mode": report.get("run_mode"),
        "git_commit": report.get("git_commit", "unknown"),
        "dataset_fingerprint": report.get("dataset_fingerprint", ""),
        "commands": list(report_manifest.get("commands") or []),
        "sample_size": int(report.get("total_cases", 0)),
        "metric_definitions": {
            "pass_rate": "passed / total_cases",
            "error_rate": "error / total_cases",
            "avg_score": "arithmetic mean of per-case scores",
        },
        "limitations": [
            "This evidence contains aggregate metrics only.",
            "Deterministic or smoke results do not represent live-model latency or quality.",
        ],
        "replaced_existing_baseline": replaced,
    }


def render_markdown_report(summary: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        f"# Benchmark Baseline: {manifest['baseline_id']}",
        "",
        f"- Run mode: `{summary.get('run_mode')}`",
        f"- Git commit: `{summary.get('git_commit')}`",
        f"- Dataset: `{summary.get('dataset_fingerprint')}`",
        f"- Sample size: {summary.get('total_cases', 0)}",
        f"- Pass rate: {summary.get('pass_rate', 0.0):.2%}",
        f"- Error rate: {summary.get('error_rate', 0.0):.2%}",
        f"- Average score: {summary.get('avg_score', 0.0):.3f}",
        "",
        "## Category metrics",
        "",
        "| Category | Cases | Passed | Failed | Error | Pass rate | Avg score |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, metrics in summary.get("category_metrics", {}).items():
        lines.append(
            f"| {category} | {metrics.get('count', 0)} | {metrics.get('passed', 0)} | "
            f"{metrics.get('failed', 0)} | {metrics.get('error', 0)} | "
            f"{metrics.get('pass_rate', 0.0):.2%} | {metrics.get('avg_score', 0.0):.3f} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in manifest["limitations"])
    return "\n".join(lines) + "\n"


def promote_baseline(
    report_path: Path,
    *,
    baseline_id: str,
    benchmarks_root: Path | None = None,
    replace: bool = False,
) -> Path:
    if not BASELINE_ID_PATTERN.fullmatch(baseline_id):
        raise BaselinePromotionError("Baseline ID must be 2-64 lowercase safe characters")
    report = load_eval_result(report_path)
    if is_legacy_report(report):
        raise BaselinePromotionError("Legacy reports cannot be promoted")
    regression = check_regression(report)
    if regression.overall_status != "PASS":
        raise BaselinePromotionError(
            "Only reports that pass the regression gate can be promoted"
        )

    root = benchmarks_root or default_benchmarks_root()
    target = root / "baselines" / baseline_id
    existed = target.exists()
    if existed and not replace:
        raise BaselinePromotionError(f"Baseline already exists: {baseline_id}")
    target.mkdir(parents=True, exist_ok=True)

    summary = build_sanitized_summary(report)
    manifest = build_manifest(
        report,
        baseline_id=baseline_id,
        source_report=report_path,
        replaced=existed,
    )
    (target / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (target / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (target / "report.md").write_text(
        render_markdown_report(summary, manifest),
        encoding="utf-8",
    )
    return target
