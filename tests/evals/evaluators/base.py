"""Shared assertion execution for SmartClass evaluations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Optional

import yaml

from app.core.evaluation import AssertionType, EvalAssertion, EvalCase, EvalResult

AssertionResult = dict[str, Any]
AssertionHandler = Callable[[EvalAssertion, dict[str, Any]], AssertionResult | Awaitable[AssertionResult]]


class UnsupportedAssertionError(ValueError):
    """Raised when a declared assertion has no executable handler."""


class JudgeEvaluationError(RuntimeError):
    """Raised when a judge assertion cannot produce a trustworthy score."""


class BaseEvaluator(ABC):
    """Base evaluator with an explicit assertion registry."""

    def __init__(self, rubric_path: Optional[Path] = None):
        self.rubric = self._load_rubric(rubric_path) if rubric_path else None
        self.judge_model: Any = None

    @abstractmethod
    async def evaluate(self, case: EvalCase) -> EvalResult:
        """Execute one evaluation case."""

    @classmethod
    def supported_assertion_types(cls) -> set[AssertionType]:
        return {
            AssertionType.ROUTE_MATCH,
            AssertionType.CONTAINS,
            AssertionType.NOT_CONTAINS,
            AssertionType.RESPONSE_QUALITY,
            AssertionType.MEMORY_CHECK,
            AssertionType.EXTRACTION_QUALITY,
            AssertionType.HALLUCINATION_CHECK,
            AssertionType.COUNT_CHECK,
            AssertionType.ENCODING_CHECK,
        }

    def _assertion_handlers(self) -> dict[AssertionType, AssertionHandler]:
        return {
            AssertionType.ROUTE_MATCH: self._check_route_match,
            AssertionType.CONTAINS: self._check_contains,
            AssertionType.NOT_CONTAINS: self._check_not_contains,
            AssertionType.RESPONSE_QUALITY: self._check_response_quality,
            AssertionType.MEMORY_CHECK: self._check_memory_check,
            AssertionType.EXTRACTION_QUALITY: self._check_extraction_quality,
            AssertionType.HALLUCINATION_CHECK: self._check_hallucination_check,
            AssertionType.COUNT_CHECK: self._check_count_check,
            AssertionType.ENCODING_CHECK: self._check_encoding_check,
        }

    def _load_rubric(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    async def _check_assertion(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        handler = self._assertion_handlers().get(assertion.type)
        if handler is None:
            raise UnsupportedAssertionError(f"Unsupported assertion type: {assertion.type.value}")
        result = handler(assertion, actual)
        if isinstance(result, Awaitable):
            return await result
        return result

    @staticmethod
    def _isolated_runtime_ids(case: EvalCase, run_id: str) -> tuple[str, str]:
        """Prevent persistent checkpointer and memory state leaking between eval runs."""
        original_thread = str(case.input.get("thread_id") or "eval_thread")
        original_user = str(case.input.get("user_id") or "eval_user")
        suffix = run_id.removeprefix("eval_")
        return f"{original_thread}__{suffix}", f"{original_user}__{suffix}"

    @staticmethod
    def _build_graph_input(case: EvalCase) -> dict[str, Any]:
        """Translate declared YAML context into the graph's stable input fields."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages = []
        message_types = {
            "assistant": AIMessage,
            "ai": AIMessage,
            "user": HumanMessage,
            "human": HumanMessage,
            "system": SystemMessage,
        }
        for item in (case.context or {}).get("chat_history") or []:
            if not isinstance(item, dict):
                continue
            message_type = message_types.get(str(item.get("role") or "").casefold())
            content = str(item.get("content") or "")
            if message_type is not None and content:
                messages.append(message_type(content=content))
        messages.append(HumanMessage(content=str(case.input["message"])))

        input_data: dict[str, Any] = {"messages": messages}
        if case.input.get("plan_id") is not None:
            input_data["plan_id"] = case.input["plan_id"]

        available_artifacts = (case.context or {}).get("available_artifacts") or []
        if available_artifacts:
            input_data["artifact_catalog"] = [
                {
                    **artifact,
                    "id": artifact.get("artifact_id") or artifact.get("id"),
                    "type": artifact.get("artifact_type") or artifact.get("type"),
                }
                for artifact in available_artifacts
                if isinstance(artifact, dict)
            ]
        return input_data

    def _base_result(self, assertion: EvalAssertion) -> AssertionResult:
        return {
            "assertion_type": assertion.type.value,
            "field": assertion.field,
            "weight": assertion.weight,
        }

    def _check_route_match(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._get_nested_field(actual, assertion.field)
        passed = field_value == assertion.expected
        return {
            **self._base_result(assertion),
            "expected": assertion.expected,
            "actual": field_value,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
        }

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _contains_expectations(expected: Any) -> tuple[str, list[Any]]:
        if isinstance(expected, dict):
            if "all" in expected:
                values = expected["all"]
                return "all", values if isinstance(values, list) else [values]
            if "any" in expected:
                values = expected["any"]
                return "any", values if isinstance(values, list) else [values]
        return "any", expected if isinstance(expected, list) else [expected]

    def _check_contains(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._stringify(self._get_nested_field(actual, assertion.field))
        normalized_field_value = field_value.casefold()
        mode, expected_values = self._contains_expectations(assertion.expected)
        matched = [
            value
            for value in expected_values
            if self._stringify(value).casefold() in normalized_field_value
        ]
        passed = len(matched) == len(expected_values) if mode == "all" else bool(matched)
        score = len(matched) / len(expected_values) if expected_values else 0.0
        return {
            **self._base_result(assertion),
            "expected": expected_values,
            "match_mode": mode,
            "matched": matched,
            "passed": passed,
            "score": score,
        }

    def _check_not_contains(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._stringify(self._get_nested_field(actual, assertion.field))
        normalized_field_value = field_value.casefold()
        expected_values = assertion.expected if isinstance(assertion.expected, list) else [assertion.expected]
        expected_values = [value for value in expected_values if self._stringify(value)]
        found = [
            value
            for value in expected_values
            if self._stringify(value).casefold() in normalized_field_value
        ]
        passed = not found
        return {
            **self._base_result(assertion),
            "expected_not_found": expected_values,
            "found": found,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
        }

    async def _check_response_quality(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        if not assertion.rubric or not self.rubric:
            raise JudgeEvaluationError("Response quality check requires a loaded rubric")
        rubric_criteria = self.rubric.get(assertion.rubric)
        if not isinstance(rubric_criteria, dict):
            raise JudgeEvaluationError(f"Rubric not found: {assertion.rubric}")
        response = self._stringify(self._get_nested_field(actual, assertion.field))
        score = await self._llm_judge(response, rubric_criteria)
        passed = score >= (assertion.min_score if assertion.min_score is not None else 0.7)
        return {
            **self._base_result(assertion),
            "rubric": assertion.rubric,
            "score": score,
            "passed": passed,
        }

    async def _llm_judge(self, response: str, rubric_criteria: dict[str, Any]) -> float:
        if self.judge_model is None:
            from app.core.llm import llm

            self.judge_model = llm
        criteria_text = yaml.dump(rubric_criteria, allow_unicode=True)
        prompt = (
            "评估以下响应的质量。\n\n"
            f"评分标准：\n{criteria_text}\n\n"
            f"响应内容：\n{response}\n\n"
            "请根据标准给出 0.0-1.0 的分数，只返回数字。"
        )
        try:
            result = await self.judge_model.ainvoke(prompt)
            score = float(str(result.content).strip())
        except Exception as exc:
            raise JudgeEvaluationError(f"LLM judge failed: {exc.__class__.__name__}") from exc
        if not 0.0 <= score <= 1.0:
            raise JudgeEvaluationError(f"LLM judge returned out-of-range score: {score}")
        return score

    def _check_memory_check(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._get_nested_field(actual, assertion.field)
        expected = assertion.expected if isinstance(assertion.expected, dict) else {}
        should_exist = expected.get("should_exist", assertion.should_exist)
        should_equal = expected.get("should_equal")
        actual_exists = field_value not in (None, "", False, [], {})

        if "should_equal" in expected:
            passed = field_value == should_equal
        elif should_exist is not None:
            passed = actual_exists is bool(should_exist)
        else:
            passed = actual_exists

        memory_type = assertion.memory_check_type or expected.get("type")
        return {
            **self._base_result(assertion),
            "memory_type": memory_type,
            "should_exist": should_exist,
            "should_equal": should_equal,
            "actual": field_value,
            "actual_exists": actual_exists,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
        }

    def _check_extraction_quality(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        raise UnsupportedAssertionError(
            f"{self.__class__.__name__} does not implement extraction_quality"
        )

    def _check_hallucination_check(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._get_nested_field(actual, assertion.field)
        expected = assertion.expected
        source_field = None
        allowed_values: list[Any] = []
        forbidden_values: list[Any] = []
        if isinstance(expected, dict):
            source_field = expected.get("source_field")
            allowed_values = list(expected.get("allowed_values") or [])
            forbidden_values = list(expected.get("forbidden_values") or [])
        else:
            forbidden_values = expected if isinstance(expected, list) else [expected]

        normalized = self._stringify(field_value).strip()
        normalized_allowed = {self._stringify(value).strip().lower() for value in allowed_values}
        source_text = self._stringify(self._get_nested_field(actual, source_field)) if source_field else ""
        found = [value for value in forbidden_values if self._stringify(value) in normalized]

        if normalized.lower() in normalized_allowed:
            passed = True
        elif source_field:
            passed = bool(normalized) and normalized in source_text
        else:
            passed = not found

        return {
            **self._base_result(assertion),
            "actual": field_value,
            "source_field": source_field,
            "forbidden_values": forbidden_values,
            "found_keywords": found,
            "hallucination_keywords": forbidden_values,
            "has_hallucination": not passed,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
        }

    def _check_count_check(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._get_nested_field(actual, assertion.field)
        actual_count = len(field_value) if isinstance(field_value, (list, tuple, set, dict, str)) else field_value
        expected = assertion.expected if isinstance(assertion.expected, dict) else {"should_equal": assertion.expected}
        expected_count = expected.get("should_equal")
        passed = actual_count == expected_count
        return {
            **self._base_result(assertion),
            "actual_count": actual_count,
            "expected_count": expected_count,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
        }

    def _check_encoding_check(self, assertion: EvalAssertion, actual: dict[str, Any]) -> AssertionResult:
        field_value = self._get_nested_field(actual, assertion.field)
        try:
            text = self._stringify(field_value)
            round_trip = text.encode("utf-8", errors="strict").decode("utf-8", errors="strict")
            passed = round_trip == text and "\ufffd" not in text
            error = None
        except UnicodeError as exc:
            passed = False
            error = exc.__class__.__name__
        return {
            **self._base_result(assertion),
            "expected": assertion.expected,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "error": error,
        }

    def _get_nested_field(self, data: dict[str, Any], field: str | None) -> Any:
        if not field:
            return None
        value: Any = data
        for key in field.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(key)
            if value is None:
                return None
        return value
