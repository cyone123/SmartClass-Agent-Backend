"""Aggregate formal SSE load windows and process-resource samples.

The Locust JSON contains window-level percentiles rather than raw request
latencies.  The report therefore preserves each window's p50/p95 and reports
the range/max across the three repeated windows instead of pretending that
percentiles can be recomputed exactly from summaries.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

WINDOW_RE = re.compile(r"^(?P<mode>[a-z]+)-r(?P<round>\d+)-(?P<users>\d+)u\.json$")
FULL_METRIC = "/api/chat/stream SSE"
TTFT_METRIC = "/api/chat/stream:ttft SSE"
RESOURCE_FIELDS = (
    "working_set_mb",
    "private_memory_mb",
    "cpu_percent",
    "thread_count",
    "handle_count",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _round_number(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _resource_summary(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        rows = []

    summary: dict[str, Any] = {"samples": len(rows)}
    elapsed = [_number(row.get("elapsed_seconds")) for row in rows]
    elapsed = [value for value in elapsed if value is not None]
    summary["observed_seconds"] = _round_number(max(elapsed) if elapsed else None)
    for field in RESOURCE_FIELDS:
        values = [_number(row.get(field)) for row in rows]
        values = [value for value in values if value is not None]
        summary[field] = {
            "p95": _round_number(_percentile(values, 0.95)),
            "max": _round_number(max(values) if values else None),
        }
    return summary


def _metric_summary(payload: dict[str, Any], metric_name: str) -> dict[str, Any]:
    metrics = payload.get("metrics")
    value = metrics.get(metric_name) if isinstance(metrics, dict) else None
    return value if isinstance(value, dict) else {}


def _window(path: Path, mode: str, round_number: int, users: int) -> dict[str, Any]:
    payload = _read_json(path)
    full = _metric_summary(payload, FULL_METRIC)
    ttft = _metric_summary(payload, TTFT_METRIC)
    full_time = full.get("response_time_ms") if isinstance(full.get("response_time_ms"), dict) else {}
    ttft_time = ttft.get("response_time_ms") if isinstance(ttft.get("response_time_ms"), dict) else {}
    resource_path = path.with_name(f"{path.stem}.resources.csv")
    errors = payload.get("error_reasons")
    errors = errors if isinstance(errors, list) else []
    return {
        "file": path.name,
        "mode": mode,
        "round": round_number,
        "users": users,
        "requests": int(full.get("requests", 0) or 0),
        "failures": int(full.get("failures", 0) or 0),
        "failure_rate_pct": _round_number(_number(full.get("failure_rate_pct"))),
        "full_latency_ms": {
            "p50": _round_number(_number(full_time.get("p50"))),
            "p95": _round_number(_number(full_time.get("p95"))),
            "max": _round_number(_number(full_time.get("max"))),
        },
        "ttft_ms": {
            "p50": _round_number(_number(ttft_time.get("p50"))),
            "p95": _round_number(_number(ttft_time.get("p95"))),
            "max": _round_number(_number(ttft_time.get("max"))),
        },
        "error_reasons": errors,
        "resource": _resource_summary(resource_path),
    }


def _range(values: list[float]) -> dict[str, float | None]:
    return {
        "min": _round_number(min(values) if values else None),
        "max": _round_number(max(values) if values else None),
    }


def _stage(mode: str, users: int, windows: list[dict[str, Any]], expected_rounds: int) -> dict[str, Any]:
    requests = sum(int(item["requests"]) for item in windows)
    failures = sum(int(item["failures"]) for item in windows)
    full_p50 = [item["full_latency_ms"]["p50"] for item in windows if item["full_latency_ms"]["p50"] is not None]
    full_p95 = [item["full_latency_ms"]["p95"] for item in windows if item["full_latency_ms"]["p95"] is not None]
    full_max = [item["full_latency_ms"]["max"] for item in windows if item["full_latency_ms"]["max"] is not None]
    ttft_p50 = [item["ttft_ms"]["p50"] for item in windows if item["ttft_ms"]["p50"] is not None]
    ttft_p95 = [item["ttft_ms"]["p95"] for item in windows if item["ttft_ms"]["p95"] is not None]
    ttft_max = [item["ttft_ms"]["max"] for item in windows if item["ttft_ms"]["max"] is not None]
    reason_counts: Counter[str] = Counter()
    for item in windows:
        for reason in item["error_reasons"]:
            if isinstance(reason, dict):
                signature = "|".join(str(reason.get(key, "")) for key in ("category", "reason", "error_type", "message"))
                reason_counts[signature] += int(reason.get("count", 1) or 1)

    resource_fields: dict[str, Any] = {"samples": sum(item["resource"]["samples"] for item in windows)}
    observed = [item["resource"]["observed_seconds"] for item in windows if item["resource"]["observed_seconds"] is not None]
    resource_fields["observed_seconds"] = _round_number(min(observed) if observed else None)
    for field in RESOURCE_FIELDS:
        p95_values = [item["resource"][field]["p95"] for item in windows if item["resource"][field]["p95"] is not None]
        max_values = [item["resource"][field]["max"] for item in windows if item["resource"][field]["max"] is not None]
        resource_fields[field] = {
            "p95_across_windows": _round_number(max(p95_values) if p95_values else None),
            "max_across_windows": _round_number(max(max_values) if max_values else None),
        }

    return {
        "mode": mode,
        "users": users,
        "rounds_expected": expected_rounds,
        "windows_completed": len(windows),
        "requests": requests,
        "failures": failures,
        "failure_rate_pct": round(100 * failures / requests, 4) if requests else None,
        "all_windows_pass": len(windows) == expected_rounds and failures == 0 and all(item["resource"]["samples"] > 0 for item in windows),
        "full_latency_ms": {
            "p50_per_window": full_p50,
            "p50_range": _range(full_p50),
            "p95_per_window": full_p95,
            "p95_range": _range(full_p95),
            "max_across_windows": _round_number(max(full_max) if full_max else None),
        },
        "ttft_ms": {
            "p50_per_window": ttft_p50,
            "p50_range": _range(ttft_p50),
            "p95_per_window": ttft_p95,
            "p95_range": _range(ttft_p95),
            "max_across_windows": _round_number(max(ttft_max) if ttft_max else None),
        },
        "resources": resource_fields,
        "error_reasons": [{"signature": signature, "count": count} for signature, count in reason_counts.most_common()],
        "windows": windows,
    }


def _load_mode_root(mode: str, root: Path, expected_rounds: int) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        match = WINDOW_RE.match(path.name)
        if not match or match.group("mode") != mode:
            continue
        windows.append(_window(path, mode, int(match.group("round")), int(match.group("users"))))
    by_users: dict[int, list[dict[str, Any]]] = {}
    for item in windows:
        by_users.setdefault(int(item["users"]), []).append(item)
    return [_stage(mode, users, sorted(items, key=lambda item: item["round"]), expected_rounds) for users, items in sorted(by_users.items())]


def _parse_input(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("input root must be MODE=PATH")
    mode, raw_path = value.split("=", 1)
    if not mode or not raw_path:
        raise argparse.ArgumentTypeError("input root must be MODE=PATH")
    return mode, Path(raw_path)


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:g}{suffix}" if isinstance(value, (int, float)) else f"{value}{suffix}"


def _report(summary: dict[str, Any]) -> str:
    lines = [
        "# Formal SSE performance baseline",
        "",
        f"- Generated: `{summary['generated_at']}`",
        "- Workload: authenticated non-RAG `/api/chat/stream` SSE, fixed normal-chat prompt.",
        "- Matrix: 1/2/4/8 concurrent users × 3 independent 5-minute windows per mode.",
        "- Resource sample: backend process once per second; p95/max are calculated per window and the table shows the worst window.",
        "",
        "## Gate summary",
        "",
        f"- Formal gate: **{'PASS' if summary['gate']['passed'] else 'FAIL'}**",
        f"- Required windows: {summary['gate']['expected_windows_per_mode']} per mode ({summary['gate']['expected_windows']} total); completed: {summary['gate']['completed_windows']}",
        "",
        "## Results",
        "",
        "| Mode | Users | Windows | Requests | Failure rate | Full p50 range | Full p95 max | TTFT p95 max | WS max MB | Private max MB | CPU p95 % | Samples |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for stage in summary["stages"]:
        full = stage["full_latency_ms"]
        ttft = stage["ttft_ms"]
        resource = stage["resources"]
        lines.append(
            "| {mode} | {users} | {windows}/{expected} | {requests} | {failure}% | {p50_min}–{p50_max} ms | {p95} ms | {ttft} ms | {ws} | {private} | {cpu} | {samples} |".format(
                mode=stage["mode"],
                users=stage["users"],
                windows=stage["windows_completed"],
                expected=stage["rounds_expected"],
                requests=stage["requests"],
                failure=_fmt(stage["failure_rate_pct"]),
                p50_min=_fmt(full["p50_range"]["min"]),
                p50_max=_fmt(full["p50_range"]["max"]),
                p95=_fmt(full["p95_range"]["max"]),
                ttft=_fmt(ttft["p95_range"]["max"]),
                ws=_fmt(resource["working_set_mb"]["max_across_windows"]),
                private=_fmt(resource["private_memory_mb"]["max_across_windows"]),
                cpu=_fmt(resource["cpu_percent"]["p95_across_windows"]),
                samples=resource["samples"],
            )
        )
    lines.extend(
        [
            "",
            "## Observed error events",
            "",
        ]
    )
    error_stages = [stage for stage in summary["stages"] if stage["error_reasons"] or stage["failures"]]
    if error_stages:
        for stage in error_stages:
            reasons = "; ".join(f"{item['count']}× {item['signature']}" for item in stage["error_reasons"])
            if not reasons:
                reasons = "request failures without an SSE error event"
            lines.append(f"- `{stage['mode']}` {stage['users']}u: {stage['failures']} request failures; {reasons}.")
    else:
        lines.append("- None recorded in the formal windows.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The Mock mode keeps the HTTP/SSE/auth/orchestration path while replacing upstream model time with a deterministic local response. The live-vs-mock latency gap is therefore an attribution aid, not a claim that Mock reproduces model quality.",
            "",
            "Error details are retained in `summary.json` using the benchmark harness's redacted error taxonomy. Raw prompts, credentials, tokens, and authorization headers are not part of the evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", action="append", required=True, type=_parse_input, metavar="MODE=PATH")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    stages: list[dict[str, Any]] = []
    for mode, root in args.input_root:
        stages.extend(_load_mode_root(mode, root, args.rounds))
    expected_windows_per_mode = args.rounds * 4
    expected_windows = len(args.input_root) * expected_windows_per_mode
    completed_windows = sum(stage["windows_completed"] for stage in stages)
    passed = bool(stages) and completed_windows == expected_windows and all(stage["all_windows_pass"] for stage in stages)
    summary = {
        "schema_version": "1.0",
        "benchmark": "sse-chat-load-formal-baseline",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "matrix": {"rounds": args.rounds, "concurrency_stages": [1, 2, 4, 8], "input_modes": [mode for mode, _ in args.input_root]},
        "gate": {
            "passed": passed,
            "expected_windows_per_mode": expected_windows_per_mode,
            "expected_windows": expected_windows,
            "completed_windows": completed_windows,
        },
        "stages": stages,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "report.md").write_text(_report(summary), encoding="utf-8")
    print(json.dumps({"gate_passed": passed, "expected_windows": expected_windows, "completed_windows": completed_windows}, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
