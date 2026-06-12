"""ExtractionEvaluator 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.evaluation import (
    EvalAssertion,
    EvalCase,
    AssertionType,
    EvalCaseStatus,
)
from tests.evals.evaluators.extraction_evaluator import ExtractionEvaluator


@pytest.fixture
def evaluator():
    """创建评估器实例"""
    return ExtractionEvaluator()


class TestCheckExtractionQuality:
    """测试 _check_extraction_quality 方法"""

    def test_extraction_quality_all_fields_present(self, evaluator):
        """所有必需字段都存在的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.7,
        )

        actual = {
            "teaching_metadata": {
                "subject": "数学",
                "grade": "高中二年级",
                "topic": "圆的性质",
                "is_complete": True,
            }
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["assertion_type"] == "extraction_quality"
        assert result["field"] == "teaching_metadata"
        assert result["completeness_score"] == 1.0
        assert result["missing_fields"] == []
        assert result["is_marked_complete"] is True
        # 综合评分 = 1.0 * 0.7 + 1.0 * 0.3 = 1.0
        assert result["final_score"] == 1.0
        assert result["score"] == 1.0
        assert result["passed"] is True
        assert result["weight"] == 1.0

    def test_extraction_quality_missing_one_field(self, evaluator):
        """缺失一个字段的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.7,
        )

        actual = {
            "teaching_metadata": {
                "subject": "英语",
                "grade": "初中三年级",
                # 缺少 topic
                "is_complete": True,
            }
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["completeness_score"] == 0.75  # 1.0 - 1/4
        assert result["missing_fields"] == ["topic"]
        assert result["is_marked_complete"] is True
        # 综合评分 = 0.75 * 0.7 + 1.0 * 0.3 = 0.525 + 0.3 = 0.825
        assert result["final_score"] == pytest.approx(0.825)
        assert result["score"] == pytest.approx(0.825)
        assert result["passed"] is True

    def test_extraction_quality_missing_multiple_fields(self, evaluator):
        """缺失多个字段的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.7,
        )

        actual = {
            "teaching_metadata": {
                "subject": "物理",
                # 缺少 grade
                # 缺少 topic
                "is_complete": False,
            }
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["completeness_score"] == 0.5  # 1.0 - 2/4
        assert set(result["missing_fields"]) == {"grade", "topic"}
        assert result["is_marked_complete"] is False
        # 综合评分 = 0.5 * 0.7 + 0.0 * 0.3 = 0.35
        assert result["final_score"] == pytest.approx(0.35)
        assert result["passed"] is False  # 0.35 < 0.7

    def test_extraction_quality_all_fields_missing(self, evaluator):
        """所有字段都缺失的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.7,
        )

        actual = {
            "teaching_metadata": {}
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["completeness_score"] == 0.0  # 1.0 - 4/4
        assert set(result["missing_fields"]) == {"subject", "grade", "topic", "is_complete"}
        assert result["is_marked_complete"] is False
        # 综合评分 = 0.0 * 0.7 + 0.0 * 0.3 = 0.0
        assert result["final_score"] == 0.0
        assert result["passed"] is False

    def test_extraction_quality_custom_min_score(self, evaluator):
        """自定义最小分数的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.5,  # 自定义最小分数
        )

        actual = {
            "teaching_metadata": {
                "subject": "化学",
                "grade": "高中一年级",
                # 缺少 topic
                "is_complete": False,
            }
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        # 综合评分 = 0.75 * 0.7 + 0.0 * 0.3 = 0.525
        assert result["final_score"] == pytest.approx(0.525)
        assert result["passed"] is True  # 0.525 >= 0.5

    def test_extraction_quality_nested_field(self, evaluator):
        """嵌套字段的情况"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="output.teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.7,
        )

        actual = {
            "output": {
                "teaching_metadata": {
                    "subject": "生物",
                    "grade": "初中一年级",
                    "topic": "细胞学说",
                    "is_complete": True,
                }
            }
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["completeness_score"] == 1.0
        assert result["missing_fields"] == []
        assert result["passed"] is True

    def test_extraction_quality_none_field_value(self, evaluator):
        """字段值为 None 的情况（视为缺失）"""
        # 准备测试数据
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_metadata",
            expected={},
            weight=1.0,
            min_score=0.7,
        )

        actual = {
            "teaching_metadata": {
                "subject": "地理",
                "grade": None,  # 显式设置为 None
                "topic": "地球的结构",
                "is_complete": True,
            }
        }

        # 执行检查
        result = evaluator._check_extraction_quality(assertion, actual)

        # 验证结果
        assert result["completeness_score"] == 0.75  # 1.0 - 1/4
        assert result["missing_fields"] == ["grade"]
        assert result["passed"] is True


class TestExtractionEvaluatorInitialization:
    """测试 ExtractionEvaluator 初始化"""

    def test_initialization(self):
        """测试初始化"""
        evaluator = ExtractionEvaluator()
        assert evaluator is not None
        assert evaluator._runtime is None

    def test_initialization_with_rubric_path(self, tmp_path):
        """测试使用 rubric 路径初始化"""
        import yaml

        # 创建临时 rubric 文件
        rubric_path = tmp_path / "rubric.yaml"
        rubric_data = {
            "extraction_quality": {
                "excellent": "All required fields present and complete",
                "good": "Most fields present",
            }
        }
        with open(rubric_path, "w", encoding="utf-8") as f:
            yaml.dump(rubric_data, f, allow_unicode=True)

        # 初始化评估器
        evaluator = ExtractionEvaluator(rubric_path=rubric_path)
        assert evaluator.rubric is not None
        assert "extraction_quality" in evaluator.rubric
