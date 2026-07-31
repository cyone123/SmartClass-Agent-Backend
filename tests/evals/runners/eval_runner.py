"""Strict evaluation runner and versioned report generation."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Optional

from app.core.evaluation import (
    EvalCase,
    EvalCaseStatus,
    EvalCategoryMetrics,
    EvalReport,
    EvalResult,
)
from tests.evals.evaluators import (
    BaseEvaluator,
    ContextCompressionEvaluator,
    ExtractionEvaluator,
    IntentEvaluator,
    MemoryEvaluator,
)
from tests.evals.manifest import build_run_manifest, sanitize_model_summary
from tests.evals.suite_validation import load_cases_strict


class EvalRunner:
    """Run a validated evaluation suite and persist a schema-versioned report."""

    def __init__(
        self,
        cases_dir: Path,
        results_dir: Path,
        *,
        run_mode: Literal["deterministic", "model-eval", "smoke", "mixed"] = "model-eval",
        model: dict[str, Any] | None = None,
        command_args: list[str] | None = None,
    ):
        self.cases_dir = cases_dir
        self.results_dir = results_dir
        self.run_mode = run_mode
        self.model = sanitize_model_summary(model) if model is not None else None
        self.command_args = list(command_args or [])
        self.evaluators: dict[str, BaseEvaluator] = {
            "intent_recognition": IntentEvaluator(),
            "memory_retrieval": MemoryEvaluator(),
            "memory_write": MemoryEvaluator(),
            "memory_update": MemoryEvaluator(),
            "extraction_quality": ExtractionEvaluator(),
            "context_compression": ContextCompressionEvaluator(),
        }

    def load_cases(self, category: Optional[str] = None) -> list[EvalCase]:
        return load_cases_strict(self.cases_dir, category=category)

    async def run_suite(
        self,
        category: Optional[str] = None,
        case_ids: Optional[list[str]] = None,
    ) -> EvalReport:
        cases = self.load_cases(category)
        if case_ids:
            requested = set(case_ids)
            cases = [case for case in cases if case.case_id in requested]
            missing = sorted(requested - {case.case_id for case in cases})
            if missing:
                raise ValueError(f"Unknown case IDs: {', '.join(missing)}")

        if not cases:
            return self._empty_report()

        print(f"[START] Running {len(cases)} evaluation cases...")
        started_at = time.perf_counter()
        results: list[EvalResult] = []

        for case in cases:
            print(f"  [{case.case_id}] {case.description}...")
            evaluator = self.evaluators.get(case.category)
            if evaluator is None:
                raise ValueError(f"No evaluator registered for category: {case.category}")
            result = await evaluator.evaluate(case)
            results.append(result)
            status_icon = "[PASS]" if result.status == EvalCaseStatus.PASSED else "[FAIL]"
            print(f"    {status_icon} {result.status.value} (score: {result.score:.2f})")

        report = self._generate_report(results, time.perf_counter() - started_at, cases)
        self._save_report(report)
        return report

    def _manifest(self):
        return build_run_manifest(
            cases_dir=self.cases_dir,
            model=self.model,
            commands=["python -m tests.evals.cli run" + "".join(f" {arg}" for arg in self.command_args)],
        )

    def _empty_report(self) -> EvalReport:
        manifest = self._manifest()
        return EvalReport(
            suite_id=f"eval_{int(time.time())}",
            total_cases=0,
            passed=0,
            failed=0,
            error=0,
            pass_rate=0.0,
            error_rate=0.0,
            avg_score=0.0,
            category_scores={},
            category_metrics={},
            results=[],
            execution_time=0.0,
            run_mode=self.run_mode,
            dataset_fingerprint=manifest.dataset_fingerprint,
            git_commit=manifest.git_commit,
            repository_dirty=manifest.repository_dirty,
            source_fingerprint=manifest.source_fingerprint,
            model=manifest.model,
            environment=manifest.environment,
            manifest=manifest,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _generate_report(
        self,
        results: list[EvalResult],
        exec_time: float,
        cases: list[EvalCase],
    ) -> EvalReport:
        passed = sum(result.status == EvalCaseStatus.PASSED for result in results)
        failed = sum(result.status == EvalCaseStatus.FAILED for result in results)
        error = sum(result.status == EvalCaseStatus.ERROR for result in results)
        total = len(results)
        avg_score = sum(result.score for result in results) / total if total else 0.0
        case_categories = {case.case_id: case.category for case in cases}

        grouped: dict[str, list[EvalResult]] = {}
        for result in results:
            category = case_categories[result.case_id]
            grouped.setdefault(category, []).append(result)

        category_metrics: dict[str, EvalCategoryMetrics] = {}
        for category, category_results in sorted(grouped.items()):
            count = len(category_results)
            category_modes = {item.run_mode for item in category_results}
            category_mode = next(iter(category_modes)) if len(category_modes) == 1 else "mixed"
            category_passed = sum(item.status == EvalCaseStatus.PASSED for item in category_results)
            category_failed = sum(item.status == EvalCaseStatus.FAILED for item in category_results)
            category_error = sum(item.status == EvalCaseStatus.ERROR for item in category_results)
            category_metrics[category] = EvalCategoryMetrics(
                run_mode=category_mode,
                count=count,
                passed=category_passed,
                failed=category_failed,
                error=category_error,
                pass_rate=category_passed / count if count else 0.0,
                error_rate=category_error / count if count else 0.0,
                avg_score=(
                    sum(item.score for item in category_results) / count if count else 0.0
                ),
            )

        manifest = self._manifest()
        result_modes = {result.run_mode for result in results}
        report_mode = next(iter(result_modes)) if len(result_modes) == 1 else "mixed"
        return EvalReport(
            suite_id=f"eval_{int(time.time())}",
            total_cases=total,
            passed=passed,
            failed=failed,
            error=error,
            pass_rate=passed / total if total else 0.0,
            error_rate=error / total if total else 0.0,
            avg_score=avg_score,
            category_scores={
                category: metrics.avg_score for category, metrics in category_metrics.items()
            },
            category_metrics=category_metrics,
            results=results,
            execution_time=exec_time,
            run_mode=report_mode,
            dataset_fingerprint=manifest.dataset_fingerprint,
            git_commit=manifest.git_commit,
            repository_dirty=manifest.repository_dirty,
            source_fingerprint=manifest.source_fingerprint,
            model=manifest.model,
            environment=manifest.environment,
            manifest=manifest,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _save_report(self, report: EvalReport) -> Path:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.results_dir / f"{report.suite_id}.json"
        with open(report_path, "w", encoding="utf-8") as file:
            json.dump(report.model_dump(mode="json"), file, indent=2, ensure_ascii=False)
        print(f"\n[SAVED] Report saved to: {report_path}")
        return report_path
