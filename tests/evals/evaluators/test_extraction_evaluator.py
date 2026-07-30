from __future__ import annotations

from app.core.evaluation import AssertionType, EvalAssertion
from tests.evals.evaluators.extraction_evaluator import ExtractionEvaluator


def _assertion(*, complete: bool, min_score: float = 0.7) -> EvalAssertion:
    return EvalAssertion(
        type=AssertionType.EXTRACTION_QUALITY,
        field="teaching_metadata",
        expected={"complete": complete},
        min_score=min_score,
    )


def test_complete_metadata_scores_one() -> None:
    evaluator = ExtractionEvaluator()
    result = evaluator._check_extraction_quality(
        _assertion(complete=True),
        {
            "teaching_metadata": {
                "subject": "数学",
                "grade": "高二",
                "topic": "三角函数",
                "is_complete": True,
            }
        },
    )
    assert result["missing_fields"] == []
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_incomplete_expectation_passes_only_when_marked_incomplete() -> None:
    evaluator = ExtractionEvaluator()
    incomplete = evaluator._check_extraction_quality(
        _assertion(complete=False, min_score=0.0),
        {"teaching_metadata": {"subject": None, "is_complete": False}},
    )
    incorrectly_complete = evaluator._check_extraction_quality(
        _assertion(complete=False, min_score=0.0),
        {
            "teaching_metadata": {
                "subject": "数学",
                "grade": "高一",
                "topic": "函数",
                "is_complete": True,
            }
        },
    )
    assert incomplete["passed"] is True
    assert incorrectly_complete["passed"] is False


def test_missing_content_fields_lower_complete_score() -> None:
    evaluator = ExtractionEvaluator()
    result = evaluator._check_extraction_quality(
        _assertion(complete=True),
        {
            "teaching_metadata": {
                "subject": "物理",
                "grade": None,
                "topic": None,
                "is_complete": True,
            }
        },
    )
    assert set(result["missing_fields"]) == {"grade", "topic"}
    assert result["passed"] is False
