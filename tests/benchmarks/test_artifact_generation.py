from __future__ import annotations

from pathlib import Path

from tests.benchmarks.artifact_generation import (
    aggregate_report,
    cases_fingerprint,
    classify_failure,
    load_cases,
)


def _attempt(artifact_type: str, *, ready: bool = True, valid: bool = True, quality: bool = True) -> dict:
    return {
        "artifact_type": artifact_type,
        "status": "ready" if ready else "failed",
        "failure_category": None if ready else "timeout",
        "metrics": {
            "duration_ms": 1000,
            "llm_call_count": 2,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "tool_call_count": 3,
            "workspace_execution_count": 1,
        },
        "validation": {
            "technical_pass": valid,
            "quality_pass": quality,
            "quality_score": 90,
        }
        if ready
        else None,
    }


def test_loads_exactly_five_cross_subject_cases() -> None:
    cases = load_cases()

    assert len(cases) == 5
    assert len({case.case_id for case in cases}) == 5
    assert len({case.subject for case in cases}) == 5
    assert cases_fingerprint().startswith("sha256:")


def test_aggregate_separates_ready_valid_and_quality_rates() -> None:
    attempts = [
        _attempt("ppt"),
        _attempt("docx", valid=False, quality=False),
        _attempt("html-game", ready=False, valid=False, quality=False),
    ]
    report = {
        "attempts": attempts,
        "batches": [{"all_ready": False, "all_technical_valid": False, "duration_ms": 1200}],
    }

    aggregate = aggregate_report(report, expected_attempts=3)

    assert aggregate["overall"]["pipeline_ready_rate_pct"] == 66.67
    assert aggregate["overall"]["technical_valid_rate_pct"] == 33.33
    assert aggregate["overall"]["usable_artifact_rate_pct"] == 33.33
    assert aggregate["evidence_gate_passed"] is True
    assert aggregate["product_targets_met"] is False


def test_incomplete_sample_fails_evidence_gate() -> None:
    report = {
        "attempts": [_attempt("ppt")],
        "batches": [],
    }

    aggregate = aggregate_report(report, expected_attempts=3)

    assert aggregate["evidence_gate"]["sample_complete"] is False
    assert aggregate["evidence_gate_passed"] is False


def test_failure_classification_is_bounded() -> None:
    assert classify_failure("request timed out") == "timeout"
    assert classify_failure("Cannot find module pptxgenjs") == "dependency"
    assert classify_failure("No generated artifact file was detected") == "no_output"
    assert classify_failure("Connection error.") == "model"
    assert classify_failure(None) is None


def test_case_file_is_inside_benchmark_package() -> None:
    case_path = Path(__file__).with_name("artifact_cases.yaml")
    assert case_path.is_file()
