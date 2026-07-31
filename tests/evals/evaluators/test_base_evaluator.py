from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.evaluation import AssertionType, EvalAssertion, EvalCase
from tests.evals.evaluators.base import BaseEvaluator, JudgeEvaluationError


class ConcreteEvaluator(BaseEvaluator):
    async def evaluate(self, case):
        raise NotImplementedError


@pytest.fixture
def evaluator() -> ConcreteEvaluator:
    return ConcreteEvaluator()


def test_registry_executes_all_deterministic_assertions(evaluator: ConcreteEvaluator) -> None:
    actual = {
        "route": "chat",
        "text": "数学 互动式教学",
        "items": [1, 2],
        "missing": None,
    }
    assertions = [
        EvalAssertion(type=AssertionType.ROUTE_MATCH, field="route", expected="chat"),
        EvalAssertion(type=AssertionType.CONTAINS, field="text", expected={"all": ["数学", "互动"]}),
        EvalAssertion(type=AssertionType.NOT_CONTAINS, field="text", expected=["密码"]),
        EvalAssertion(type=AssertionType.COUNT_CHECK, field="items", expected={"should_equal": 2}),
        EvalAssertion(type=AssertionType.ENCODING_CHECK, field="text", expected="utf8_valid"),
        EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="missing",
            expected={"should_exist": False},
        ),
    ]

    results = [asyncio.run(evaluator._check_assertion(assertion, actual)) for assertion in assertions]
    assert all(result["passed"] for result in results)


def test_contains_defaults_to_any_but_supports_all(evaluator: ConcreteEvaluator) -> None:
    any_result = asyncio.run(evaluator._check_assertion(
        EvalAssertion(type=AssertionType.CONTAINS, field="value", expected=["a", "z"]),
        {"value": "abc"},
    ))
    all_result = asyncio.run(evaluator._check_assertion(
        EvalAssertion(type=AssertionType.CONTAINS, field="value", expected={"all": ["a", "z"]}),
        {"value": "abc"},
    ))
    assert any_result["passed"] is True
    assert all_result["passed"] is False


def test_contains_is_case_insensitive_for_mixed_language_memory(
    evaluator: ConcreteEvaluator,
) -> None:
    result = asyncio.run(evaluator._check_assertion(
        EvalAssertion(
            type=AssertionType.CONTAINS,
            field="value",
            expected={"all": ["AP Biology", "critical thinking"]},
        ),
        {"value": "AP Biology and Critical thinking"},
    ))
    assert result["passed"] is True


def test_hallucination_check_can_compare_with_source(evaluator: ConcreteEvaluator) -> None:
    assertion = EvalAssertion(
        type=AssertionType.HALLUCINATION_CHECK,
        field="metadata.subject",
        expected={
            "source_field": "input_message",
            "allowed_values": [None, "", "未知"],
        },
    )
    assert (
        asyncio.run(evaluator._check_assertion(
            assertion,
            {"metadata": {"subject": "数学"}, "input_message": "设计数学课程"},
        ))
    )["passed"]
    assert not (
        asyncio.run(evaluator._check_assertion(
            assertion,
            {"metadata": {"subject": "物理"}, "input_message": "设计数学课程"},
        ))
    )["passed"]


def test_judge_failure_raises_instead_of_returning_half_score(
    evaluator: ConcreteEvaluator,
) -> None:
    evaluator.rubric = {"quality": {"good": "relevant"}}

    class FailingJudge:
        async def ainvoke(self, prompt):
            raise RuntimeError("judge unavailable")

    evaluator.judge_model = FailingJudge()
    assertion = EvalAssertion(
        type=AssertionType.RESPONSE_QUALITY,
        field="response",
        expected=True,
        rubric="quality",
    )
    with pytest.raises(JudgeEvaluationError):
        asyncio.run(evaluator._check_assertion(assertion, {"response": "answer"}))


def test_nested_field_returns_none_for_broken_path(evaluator: ConcreteEvaluator) -> None:
    assert evaluator._get_nested_field({"user": "not-a-dict"}, "user.name") is None


def test_graph_input_injects_declared_history_and_artifact_catalog(
    evaluator: ConcreteEvaluator,
) -> None:
    case = EvalCase(
        case_id="artifact-revision",
        category="intent_recognition",
        description="fixture",
        version="1.0",
        input={
            "user_id": "eval-user",
            "thread_id": "eval-thread",
            "plan_id": 3,
            "message": "修改第三页标题",
        },
        context={
            "chat_history": [{"role": "assistant", "content": "已生成 PPT"}],
            "available_artifacts": [
                {
                    "artifact_id": 101,
                    "artifact_type": "ppt",
                    "title": "课程.pptx",
                    "status": "ready",
                }
            ],
        },
        expectations={},
        assertions=[],
        metadata={},
    )

    graph_input = evaluator._build_graph_input(case)

    assert isinstance(graph_input["messages"][0], AIMessage)
    assert isinstance(graph_input["messages"][1], HumanMessage)
    assert graph_input["plan_id"] == 3
    assert graph_input["artifact_catalog"][0]["id"] == 101
    assert graph_input["artifact_catalog"][0]["type"] == "ppt"


def test_runtime_ids_are_unique_per_run(evaluator: ConcreteEvaluator) -> None:
    case = EvalCase(
        case_id="isolated",
        category="intent_recognition",
        description="fixture",
        version="1.0",
        input={"user_id": "user", "thread_id": "thread", "message": "hello"},
        context={},
        expectations={},
        assertions=[],
        metadata={},
    )

    first = evaluator._isolated_runtime_ids(case, "eval_first")
    second = evaluator._isolated_runtime_ids(case, "eval_second")

    assert first == ("thread__first", "user__first")
    assert second == ("thread__second", "user__second")
