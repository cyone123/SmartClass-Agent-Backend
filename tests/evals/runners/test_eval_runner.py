from __future__ import annotations

from pathlib import Path

import pytest

from app.core.evaluation import EvalCase, EvalCaseStatus, EvalResult
from tests.evals.evaluators import ContextCompressionEvaluator
from tests.evals.runners import EvalRunner


def _case(case_id: str, category: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        category=category,
        description="fixture",
        version="1.0",
        input={"message": "hello"},
        context={},
        expectations={},
        assertions=[],
        metadata={},
    )


def _result(
    case_id: str,
    status: EvalCaseStatus,
    score: float,
    *,
    run_mode: str = "smoke",
) -> EvalResult:
    return EvalResult(
        case_id=case_id,
        run_id=f"run-{case_id}",
        status=status,
        score=score,
        assertion_results=[],
        actual_output={},
        execution_time=0.1,
        run_mode=run_mode,
    )


def test_runner_registers_all_current_categories(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path / "cases", tmp_path / "results")
    assert set(runner.evaluators) == {
        "intent_recognition",
        "memory_retrieval",
        "memory_write",
        "memory_update",
        "extraction_quality",
        "context_compression",
    }
    assert isinstance(runner.evaluators["context_compression"], ContextCompressionEvaluator)


def test_runner_loads_current_24_cases_by_yaml_category(tmp_path: Path) -> None:
    cases_dir = Path(__file__).parents[1] / "cases"
    runner = EvalRunner(cases_dir, tmp_path / "results")
    assert len(runner.load_cases()) == 24
    assert len(runner.load_cases("memory_retrieval")) == 3
    assert len(runner.load_cases("memory_update")) == 1
    assert len(runner.load_cases("context_compression")) == 4


def test_report_keeps_pass_rate_and_average_score_separate(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path / "cases", tmp_path / "results", run_mode="smoke")
    cases = [_case("a", "intent_recognition"), _case("b", "intent_recognition")]
    report = runner._generate_report(
        [
            _result("a", EvalCaseStatus.PASSED, 0.8),
            _result("b", EvalCaseStatus.FAILED, 0.4),
        ],
        0.2,
        cases,
    )
    assert report.pass_rate == 0.5
    assert report.avg_score == pytest.approx(0.6)
    metrics = report.category_metrics["intent_recognition"]
    assert metrics.pass_rate == 0.5
    assert metrics.avg_score == pytest.approx(0.6)


def test_report_counts_errors_independently(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path / "cases", tmp_path / "results", run_mode="smoke")
    cases = [_case("a", "memory_retrieval")]
    report = runner._generate_report(
        [_result("a", EvalCaseStatus.ERROR, 0.0)],
        0.1,
        cases,
    )
    assert report.error == 1
    assert report.error_rate == 1.0
    assert report.category_metrics["memory_retrieval"].error == 1


def test_report_marks_mixed_execution_modes_without_conflating_categories(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path / "cases", tmp_path / "results")
    cases = [
        _case("model-case", "intent_recognition"),
        _case("deterministic-case", "context_compression"),
    ]
    report = runner._generate_report(
        [
            _result(
                "model-case",
                EvalCaseStatus.PASSED,
                1.0,
                run_mode="model-eval",
            ),
            _result(
                "deterministic-case",
                EvalCaseStatus.PASSED,
                1.0,
                run_mode="deterministic",
            ),
        ],
        0.2,
        cases,
    )

    assert report.run_mode == "mixed"
    assert report.category_metrics["intent_recognition"].run_mode == "model-eval"
    assert report.category_metrics["context_compression"].run_mode == "deterministic"
