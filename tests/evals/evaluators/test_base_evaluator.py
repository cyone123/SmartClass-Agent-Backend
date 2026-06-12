"""BaseEvaluator 单元测试"""
import pytest
from unittest.mock import AsyncMock

from app.core.evaluation import EvalAssertion, AssertionType
from tests.evals.evaluators.base import BaseEvaluator


class ConcreteEvaluator(BaseEvaluator):
    """BaseEvaluator 的具体实现，用于测试"""

    async def evaluate(self, case):
        """实现抽象方法"""
        pass


@pytest.fixture
def evaluator():
    """创建评估器实例"""
    return ConcreteEvaluator()


class TestCheckMemoryCheck:
    """测试 _check_memory_check 方法"""

    def test_check_memory_check_exists(self, evaluator):
        """检查记忆存在的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="memory.profile",
            expected={
                "type": "profile",
                "should_exist": True,
            },
            weight=1.0,
        )

        actual = {
            "memory": {
                "profile": {"teacher_level": "intermediate", "subject": "math"},
            }
        }

        # 执行检查
        result = evaluator._check_memory_check(assertion, actual)

        # 验证结果
        assert result["assertion_type"] == "memory_check"
        assert result["field"] == "memory.profile"
        assert result["memory_type"] == "profile"
        assert result["should_exist"] is True
        assert result["actual_exists"] is True
        assert result["passed"] is True
        assert result["score"] == 1.0
        assert result["weight"] == 1.0

    def test_check_memory_check_not_exists(self, evaluator):
        """检查记忆不存在的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="memory.experience",
            expected={
                "type": "experience",
                "should_exist": False,
            },
            weight=1.0,
        )

        actual = {
            "memory": {
                "profile": {"teacher_level": "intermediate"},
                "experience": None,
            }
        }

        # 执行检查
        result = evaluator._check_memory_check(assertion, actual)

        # 验证结果
        assert result["assertion_type"] == "memory_check"
        assert result["field"] == "memory.experience"
        assert result["memory_type"] == "experience"
        assert result["should_exist"] is False
        assert result["actual_exists"] is False
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_check_memory_check_exists_but_should_not(self, evaluator):
        """检查记忆存在但不应该存在的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="memory.experience",
            expected={
                "type": "experience",
                "should_exist": False,
            },
            weight=1.0,
        )

        actual = {
            "memory": {
                "experience": [
                    {"title": "Math teaching strategy", "description": "Use interactive games"}
                ],
            }
        }

        # 执行检查
        result = evaluator._check_memory_check(assertion, actual)

        # 验证结果
        assert result["passed"] is False
        assert result["score"] == 0.0
        assert result["actual_exists"] is True

    def test_check_memory_check_not_exists_but_should(self, evaluator):
        """检查记忆不存在但应该存在的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="memory.profile",
            expected={
                "type": "profile",
                "should_exist": True,
            },
            weight=1.0,
        )

        actual = {"memory": {}}

        # 执行检查
        result = evaluator._check_memory_check(assertion, actual)

        # 验证结果
        assert result["passed"] is False
        assert result["score"] == 0.0
        assert result["actual_exists"] is False


class TestCheckHallucinationCheck:
    """测试 _check_hallucination_check 方法"""

    def test_check_hallucination_check_found(self, evaluator):
        """检测到幻觉的情况"""
        # 准备测试数据
        hallucination_keywords = ["fictional", "made-up", "imaginary"]
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,  # 使用 hallucination_check 类型需要在 AssertionType 中定义
            field="response",
            expected=hallucination_keywords,
            weight=1.0,
        )

        actual = {
            "response": "The student used a fictional character named Alex to understand the concept."
        }

        # 执行检查
        result = evaluator._check_hallucination_check(assertion, actual)

        # 验证结果
        assert result["assertion_type"] == "memory_check"
        assert result["field"] == "response"
        assert result["hallucination_keywords"] == hallucination_keywords
        assert "fictional" in result["found_keywords"]
        assert result["has_hallucination"] is True
        assert result["passed"] is False
        assert result["score"] == 0.0

    def test_check_hallucination_check_not_found(self, evaluator):
        """没有检测到幻觉的情况"""
        # 准备测试数据
        hallucination_keywords = ["fictional", "made-up", "imaginary"]
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="response",
            expected=hallucination_keywords,
            weight=1.0,
        )

        actual = {
            "response": "The student learned about photosynthesis in the classroom today."
        }

        # 执行检查
        result = evaluator._check_hallucination_check(assertion, actual)

        # 验证结果
        assert result["assertion_type"] == "memory_check"
        assert result["field"] == "response"
        assert result["hallucination_keywords"] == hallucination_keywords
        assert result["found_keywords"] == []
        assert result["has_hallucination"] is False
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_check_hallucination_check_multiple_keywords(self, evaluator):
        """检测到多个幻觉关键词的情况"""
        # 准备测试数据
        hallucination_keywords = ["fictional", "made-up", "imaginary"]
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="response",
            expected=hallucination_keywords,
            weight=1.0,
        )

        actual = {
            "response": "The fictional and made-up scenario was used to teach the concept."
        }

        # 执行检查
        result = evaluator._check_hallucination_check(assertion, actual)

        # 验证结果
        assert len(result["found_keywords"]) == 2
        assert "fictional" in result["found_keywords"]
        assert "made-up" in result["found_keywords"]
        assert result["has_hallucination"] is True
        assert result["passed"] is False
        assert result["score"] == 0.0

    def test_check_hallucination_check_single_keyword_string(self, evaluator):
        """单个关键词作为字符串的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="response",
            expected="fictional",  # 单个字符串而不是列表
            weight=1.0,
        )

        actual = {
            "response": "This is a fictional scenario."
        }

        # 执行检查
        result = evaluator._check_hallucination_check(assertion, actual)

        # 验证结果
        assert result["hallucination_keywords"] == ["fictional"]
        assert "fictional" in result["found_keywords"]
        assert result["has_hallucination"] is True
        assert result["passed"] is False
        assert result["score"] == 0.0


class TestCheckExtractionQuality:
    """测试 _check_extraction_quality 方法"""

    @pytest.mark.asyncio
    async def test_check_extraction_quality_not_implemented(self, evaluator):
        """检查提取质量未实现的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="extraction",
            expected={},
            weight=1.0,
        )

        actual = {}

        # 执行检查
        result = await evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["passed"] is False
        assert result["score"] == 0.0
        assert "not implemented" in result["error"]


class TestGetNestedField:
    """测试 _get_nested_field 方法"""

    def test_get_nested_field_single_level(self, evaluator):
        """获取单层字段"""
        data = {"name": "Alice"}
        result = evaluator._get_nested_field(data, "name")
        assert result == "Alice"

    def test_get_nested_field_multiple_levels(self, evaluator):
        """获取多层嵌套字段"""
        data = {"user": {"profile": {"name": "Bob"}}}
        result = evaluator._get_nested_field(data, "user.profile.name")
        assert result == "Bob"

    def test_get_nested_field_not_found(self, evaluator):
        """字段不存在的情况"""
        data = {"user": {"name": "Charlie"}}
        result = evaluator._get_nested_field(data, "user.age")
        assert result is None

    def test_get_nested_field_path_broken(self, evaluator):
        """路径断裂的情况"""
        data = {"user": "not_a_dict"}
        result = evaluator._get_nested_field(data, "user.profile.name")
        assert result is None
