"""评估运行器"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from app.core.evaluation import EvalCase, EvalCaseStatus, EvalReport, EvalResult
from tests.evals.evaluators import (
    BaseEvaluator,
    IntentEvaluator,
    MemoryEvaluator,
    ExtractionEvaluator,
)


class EvalRunner:
    """评估运行器"""

    def __init__(self, cases_dir: Path, results_dir: Path):
        self.cases_dir = cases_dir
        self.results_dir = results_dir
        self.evaluators: dict[str, BaseEvaluator] = {
            "intent_recognition": IntentEvaluator(),
            "memory_retrieval": MemoryEvaluator(),
            "memory_write": MemoryEvaluator(),
            "memory_update": MemoryEvaluator(),
            "extraction_quality": ExtractionEvaluator(),
        }

    def load_cases(self, category: Optional[str] = None) -> list[EvalCase]:
        """加载评估用例"""
        cases = []
        search_dir = self.cases_dir / category if category else self.cases_dir

        if not search_dir.exists():
            print(f"[WARNING] Cases directory not found: {search_dir}")
            return cases

        for yaml_file in search_dir.rglob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    cases.append(EvalCase(**data))
            except Exception as e:
                print(f"[WARNING] Failed to load case {yaml_file}: {e}")

        return cases

    async def run_suite(
        self, category: Optional[str] = None, case_ids: Optional[list[str]] = None
    ) -> EvalReport:
        """运行评估套件"""
        cases = self.load_cases(category)

        if case_ids:
            cases = [c for c in cases if c.case_id in case_ids]

        if not cases:
            print("[WARNING] No cases to run")
            return EvalReport(
                suite_id=f"eval_{int(time.time())}",
                total_cases=0,
                passed=0,
                failed=0,
                error=0,
                avg_score=0.0,
                category_scores={},
                results=[],
                execution_time=0.0,
                timestamp=datetime.utcnow().isoformat(),
            )

        print(f"[START] Running {len(cases)} evaluation cases...")

        start_time = time.time()
        results = []

        for case in cases:
            print(f"  [{case.case_id}] {case.description}...")
            evaluator = self.evaluators.get(case.category)

            if not evaluator:
                print(f"    [WARNING] No evaluator for category: {case.category}")
                continue

            result = await evaluator.evaluate(case)
            results.append(result)

            status_icon = "[PASS]" if result.status == EvalCaseStatus.PASSED else "[FAIL]"
            print(f"    {status_icon} {result.status.value} (score: {result.score:.2f})")

        # 生成报告
        report = self._generate_report(results, time.time() - start_time, cases)

        # 保存结果
        self._save_report(report)

        return report

    def _generate_report(
        self, results: list[EvalResult], exec_time: float, cases: list[EvalCase]
    ) -> EvalReport:
        """生成评估报告"""
        passed = sum(1 for r in results if r.status == EvalCaseStatus.PASSED)
        failed = sum(1 for r in results if r.status == EvalCaseStatus.FAILED)
        error = sum(1 for r in results if r.status == EvalCaseStatus.ERROR)

        avg_score = sum(r.score for r in results) / len(results) if results else 0.0

        # 按类别统计
        category_scores: dict[str, list[float]] = {}
        for result in results:
            case = next((c for c in cases if c.case_id == result.case_id), None)
            if case:
                if case.category not in category_scores:
                    category_scores[case.category] = []
                category_scores[case.category].append(result.score)

        category_avg_scores = {
            cat: sum(scores) / len(scores) for cat, scores in category_scores.items()
        }

        return EvalReport(
            suite_id=f"eval_{int(time.time())}",
            total_cases=len(results),
            passed=passed,
            failed=failed,
            error=error,
            avg_score=avg_score,
            category_scores=category_avg_scores,
            results=results,
            execution_time=exec_time,
            timestamp=datetime.utcnow().isoformat(),
        )

    def _save_report(self, report: EvalReport):
        """保存评估报告"""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.results_dir / f"{report.suite_id}.json"

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

        print(f"\n[SAVED] Report saved to: {report_path}")
