from __future__ import annotations

from pathlib import Path

import pytest

from tests.evals.check_regression import check_regression, load_eval_result

FIXTURES = Path(__file__).parent / "fixtures" / "reports"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("passing.json", "PASS"),
        ("threshold-regression.json", "FAIL"),
        ("missing-category.json", "FAIL"),
        ("runtime-error.json", "FAIL"),
        ("legacy.json", "FAIL"),
    ],
)
def test_regression_fixtures(name: str, expected: str) -> None:
    result = check_regression(load_eval_result(FIXTURES / name))
    assert result.overall_status == expected


def test_regression_uses_pass_rate_not_average_score() -> None:
    result = check_regression(load_eval_result(FIXTURES / "threshold-regression.json"))
    assert "memory_retrieval.pass_rate" in result.failed_metrics
    assert "memory_retrieval.error_count" not in result.failed_metrics
