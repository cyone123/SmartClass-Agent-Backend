"""评估器基类"""
from __future__ import annotations

import yaml
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from app.core.evaluation import EvalAssertion, EvalCase, EvalResult
from app.core.llm import llm


class BaseEvaluator(ABC):
    """评估器基类"""

    def __init__(self, rubric_path: Optional[Path] = None):
        self.rubric = self._load_rubric(rubric_path) if rubric_path else None

    @abstractmethod
    async def evaluate(self, case: EvalCase) -> EvalResult:
        """执行评估"""
        pass

    def _load_rubric(self, path: Path) -> dict[str, Any]:
        """加载评分标准"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def _check_assertion(
        self, assertion: EvalAssertion, actual: dict[str, Any]
    ) -> dict[str, Any]:
        """检查单个断言"""
        if assertion.type == "route_match":
            return self._check_route_match(assertion, actual)
        elif assertion.type == "contains":
            return self._check_contains(assertion, actual)
        elif assertion.type == "not_contains":
            return self._check_not_contains(assertion, actual)
        elif assertion.type == "response_quality":
            return await self._check_response_quality(assertion, actual)
        else:
            return {
                "assertion_type": assertion.type,
                "passed": False,
                "score": 0.0,
                "weight": assertion.weight,
                "error": f"Unknown assertion type: {assertion.type}",
            }

    def _check_route_match(
        self, assertion: EvalAssertion, actual: dict[str, Any]
    ) -> dict[str, Any]:
        """检查路由匹配"""
        field_value = self._get_nested_field(actual, assertion.field)
        passed = field_value == assertion.expected
        return {
            "assertion_type": assertion.type.value,
            "field": assertion.field,
            "expected": assertion.expected,
            "actual": field_value,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "weight": assertion.weight,
        }

    def _check_contains(
        self, assertion: EvalAssertion, actual: dict[str, Any]
    ) -> dict[str, Any]:
        """检查包含"""
        field_value = str(self._get_nested_field(actual, assertion.field) or "")
        expected_values = (
            assertion.expected
            if isinstance(assertion.expected, list)
            else [assertion.expected]
        )
        matched = [val for val in expected_values if val in field_value]
        passed = len(matched) > 0
        return {
            "assertion_type": assertion.type.value,
            "field": assertion.field,
            "expected": expected_values,
            "matched": matched,
            "passed": passed,
            "score": len(matched) / len(expected_values) if expected_values else 0.0,
            "weight": assertion.weight,
        }

    def _check_not_contains(
        self, assertion: EvalAssertion, actual: dict[str, Any]
    ) -> dict[str, Any]:
        """检查不包含"""
        field_value = self._get_nested_field(actual, assertion.field)

        # 处理字符串字段
        if isinstance(field_value, str):
            field_value_str = field_value
        # 处理对象字段
        elif field_value is not None:
            field_value_str = str(field_value)
        else:
            field_value_str = ""

        expected_values = (
            assertion.expected
            if isinstance(assertion.expected, list)
            else [assertion.expected]
        )
        found = [val for val in expected_values if val in field_value_str]
        passed = len(found) == 0
        return {
            "assertion_type": assertion.type.value,
            "field": assertion.field,
            "expected_not_found": expected_values,
            "found": found,
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "weight": assertion.weight,
        }

    async def _check_response_quality(
        self, assertion: EvalAssertion, actual: dict[str, Any]
    ) -> dict[str, Any]:
        """使用 LLM 评估响应质量"""
        if not assertion.rubric or not self.rubric:
            return {
                "assertion_type": assertion.type.value,
                "passed": False,
                "score": 0.0,
                "weight": assertion.weight,
                "error": "Response quality check requires rubric",
            }

        rubric_criteria = self.rubric.get(assertion.rubric, {})
        response = str(self._get_nested_field(actual, assertion.field) or "")

        score = await self._llm_judge(response, rubric_criteria)
        passed = score >= (assertion.min_score or 0.7)

        return {
            "assertion_type": assertion.type.value,
            "field": assertion.field,
            "rubric": assertion.rubric,
            "score": score,
            "passed": passed,
            "weight": assertion.weight,
        }

    async def _llm_judge(
        self, response: str, rubric_criteria: dict[str, Any]
    ) -> float:
        """使用 LLM 评分"""
        criteria_text = yaml.dump(rubric_criteria, allow_unicode=True)
        prompt = f"""评估以下响应的质量。

评分标准：
{criteria_text}

响应内容：
{response}

请根据标准给出 0.0-1.0 的分数，只返回数字。"""

        try:
            result = await llm.ainvoke(prompt)
            score_text = result.content.strip()
            score = float(score_text)
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5

    def _get_nested_field(self, data: dict[str, Any], field: str) -> Any:
        """获取嵌套字段值"""
        keys = field.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
            if value is None:
                return None
        return value
