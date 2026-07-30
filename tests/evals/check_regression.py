"""Fail-closed regression gate for schema-versioned evaluation reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


class RegressionCheckResult:
    def __init__(self) -> None:
        self.metrics: dict[str, dict[str, Any]] = {}
        self.overall_status = "PASS"
        self.failed_metrics: list[str] = []
        self.warnings: list[str] = []

    def add_metric(
        self,
        name: str,
        actual: float,
        expected: float,
        threshold_type: str = ">=",
    ) -> None:
        comparisons = {
            ">=": actual >= expected,
            "==": actual == expected,
            "<=": actual <= expected,
        }
        if threshold_type not in comparisons:
            raise ValueError(f"Unsupported threshold type: {threshold_type}")
        passed = comparisons[threshold_type]
        self.metrics[name] = {
            "actual": actual,
            "expected": expected,
            "threshold_type": threshold_type,
            "passed": passed,
        }
        if not passed:
            self.fail(name)

    def fail(self, name: str) -> None:
        if name not in self.failed_metrics:
            self.failed_metrics.append(name)
        self.overall_status = "FAIL"

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def default_thresholds_path() -> Path:
    return Path(__file__).with_name("regression_thresholds.yaml")


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    target = path or default_thresholds_path()
    with open(target, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict) or not isinstance(data.get("required_categories"), dict):
        raise ValueError(f"Invalid regression thresholds: {target}")
    return data


def load_eval_result(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Evaluation report must be a JSON object: {path}")
    return data


def find_latest_result(results_dir: Path) -> Path | None:
    candidates = sorted(results_dir.glob("eval_*.json"), key=lambda path: path.stat().st_mtime)
    return candidates[-1] if candidates else None


def is_legacy_report(eval_data: dict[str, Any]) -> bool:
    return str(eval_data.get("schema_version") or "").strip() != "2.0"


def check_regression(
    eval_data: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> RegressionCheckResult:
    thresholds = thresholds or load_thresholds()
    result = RegressionCheckResult()

    if is_legacy_report(eval_data):
        result.fail("schema_version")
        result.add_warning("Legacy reports are read-only and cannot pass the regression gate.")
        return result

    category_metrics = eval_data.get("category_metrics")
    if not isinstance(category_metrics, dict):
        result.fail("category_metrics")
        return result

    total_errors = int(eval_data.get("error", 0))
    result.add_metric(
        "overall.error_count",
        actual=float(total_errors),
        expected=float(thresholds.get("max_error_count", 0)),
        threshold_type="<=",
    )

    for category, rule in thresholds["required_categories"].items():
        metrics = category_metrics.get(category)
        if not isinstance(metrics, dict):
            result.fail(f"{category}.present")
            continue
        error_count = int(metrics.get("error", 0))
        pass_rate = float(metrics.get("pass_rate", 0.0))
        result.add_metric(
            f"{category}.error_count",
            actual=float(error_count),
            expected=0.0,
            threshold_type="==",
        )
        result.add_metric(
            f"{category}.pass_rate",
            actual=pass_rate,
            expected=float(rule["min_pass_rate"]),
            threshold_type=">=",
        )

    return result


def print_regression_report(eval_data: dict[str, Any], check_result: RegressionCheckResult) -> None:
    print("\n" + "=" * 70)
    print("[REGRESSION] Evaluation regression gate")
    print("=" * 70)
    for name, metric in check_result.metrics.items():
        status = "PASS" if metric["passed"] else "FAIL"
        print(
            f"[{status}] {name}: {metric['actual']:.3f} "
            f"{metric['threshold_type']} {metric['expected']:.3f}"
        )
    for missing in sorted(name for name in check_result.failed_metrics if name.endswith(".present")):
        print(f"[FAIL] {missing}: required category is missing")
    for warning in check_result.warnings:
        print(f"[WARNING] {warning}")
    print(f"Overall: {check_result.overall_status}")
    print(
        f"Summary: total={eval_data.get('total_cases', 0)}, "
        f"passed={eval_data.get('passed', 0)}, failed={eval_data.get('failed', 0)}, "
        f"error={eval_data.get('error', 0)}, pass_rate={eval_data.get('pass_rate', 0):.3f}, "
        f"avg_score={eval_data.get('avg_score', 0):.3f}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Report to check; defaults to latest local result")
    parser.add_argument("--thresholds", type=Path, help="Optional threshold configuration")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = args.report or find_latest_result(Path(__file__).with_name("results"))
    if report_path is None:
        print("[ERROR] No evaluation report found")
        return 1
    try:
        eval_data = load_eval_result(report_path)
        thresholds = load_thresholds(args.thresholds)
        check_result = check_regression(eval_data, thresholds)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print_regression_report(eval_data, check_result)
    return 0 if check_result.overall_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
