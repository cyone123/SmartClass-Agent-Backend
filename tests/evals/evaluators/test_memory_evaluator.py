"""MemoryEvaluator 单元测试"""
from __future__ import annotations

import pytest
from app.core.evaluation import (
    AssertionType,
    EvalAssertion,
    EvalCase,
    EvalCaseStatus,
)
from backend.tests.evals.evaluators.memory_evaluator import MemoryEvaluator


class TestMemoryEvaluator:
    """MemoryEvaluator 测试套件"""

    @pytest.fixture
    def evaluator(self):
        """创建评估器实例"""
        return MemoryEvaluator()

    @pytest.fixture
    def basic_memory_case(self) -> EvalCase:
        """基础记忆加载评估用例"""
        return EvalCase(
            case_id="memory_basic_load_001",
            category="memory_retrieval",
            description="测试基础记忆加载能力",
            version="1.0",
            input={
                "user_id": "eval_user_001",
                "thread_id": "eval_thread_memory_001",
                "message": "我是数学老师，需要为初中学生设计一堂几何课程",
            },
            context={
                "user_profile": {
                    "role": "teacher",
                    "subject": "数学",
                    "grade": "初中",
                },
                "available_memories": [
                    {
                        "type": "profile",
                        "content": "用户是初中数学教师，偏好使用几何画板辅助教学",
                    }
                ],
            },
            expectations={
                "should_load_profile": True,
                "should_retrieve_experiences": True,
                "should_not_expose_privacy": True,
            },
            assertions=[
                EvalAssertion(
                    type=AssertionType.MEMORY_CHECK,
                    field="profile_memory_context",
                    expected={"type": "profile", "should_exist": True},
                    weight=1.0,
                ),
                EvalAssertion(
                    type=AssertionType.NOT_CONTAINS,
                    field="profile_memory_context",
                    expected=["电话", "邮箱", "密码"],
                    weight=0.8,
                ),
            ],
            metadata={
                "author": "eval_designer",
                "created_at": "2026-06-11",
                "tags": ["memory", "profile", "baseline"],
            },
        )

    @pytest.fixture
    def experience_retrieval_case(self) -> EvalCase:
        """经验记忆检索评估用例"""
        return EvalCase(
            case_id="memory_exp_retrieval_001",
            category="memory_retrieval",
            description="测试相关经验记忆检索",
            version="1.0",
            input={
                "user_id": "eval_user_001",
                "thread_id": "eval_thread_memory_002",
                "message": "上次我用思维导图的方式讲几何，效果很好。能否用类似方法生成今天的教学设计？",
            },
            context={
                "user_profile": {
                    "role": "teacher",
                    "subject": "数学",
                },
                "available_memories": [
                    {
                        "type": "experience",
                        "content": "思维导图教学法在几何中的应用：学生理解效果提升 30%",
                    }
                ],
            },
            expectations={
                "should_retrieve_related_experience": True,
                "should_use_experience_in_response": True,
            },
            assertions=[
                EvalAssertion(
                    type=AssertionType.MEMORY_CHECK,
                    field="loaded_experience_memories",
                    expected={"type": "experience", "should_exist": True},
                    weight=1.0,
                ),
            ],
            metadata={
                "author": "eval_designer",
                "created_at": "2026-06-11",
                "tags": ["memory", "experience", "retrieval"],
            },
        )

    @pytest.mark.asyncio
    async def test_evaluator_initialization(self, evaluator):
        """测试评估器初始化"""
        assert evaluator is not None
        assert evaluator._runtime is None  # 延迟初始化

    @pytest.mark.asyncio
    async def test_get_runtime_lazy_initialization(self, evaluator):
        """测试 runtime 延迟初始化"""
        # 第一次调用应该初始化
        runtime1 = await evaluator._get_runtime()
        assert runtime1 is not None
        assert evaluator._runtime is not None

        # 第二次调用应该返回相同实例
        runtime2 = await evaluator._get_runtime()
        assert runtime2 is runtime1

    @pytest.mark.asyncio
    async def test_basic_memory_evaluation(self, evaluator, basic_memory_case):
        """测试基础记忆评估

        注：这个测试需要真实的 LangGraph 执行环境。
        如果本地环境不完整（缺少模型、存储等），会返回 ERROR 状态。
        但框架应该正确处理异常并返回有效的 EvalResult。
        """
        result = await evaluator.evaluate(basic_memory_case)

        # 验证结果结构
        assert result is not None
        assert result.case_id == basic_memory_case.case_id
        assert result.run_id.startswith("eval_")
        assert result.status in [
            EvalCaseStatus.PASSED,
            EvalCaseStatus.FAILED,
            EvalCaseStatus.ERROR,
        ]
        assert 0.0 <= result.score <= 1.0
        assert result.assertion_results is not None
        assert isinstance(result.assertion_results, list)
        assert result.actual_output is not None
        assert result.execution_time >= 0

    @pytest.mark.asyncio
    async def test_experience_retrieval_evaluation(self, evaluator, experience_retrieval_case):
        """测试经验检索评估"""
        result = await evaluator.evaluate(experience_retrieval_case)

        # 验证结果结构
        assert result is not None
        assert result.case_id == experience_retrieval_case.case_id
        assert result.status in [
            EvalCaseStatus.PASSED,
            EvalCaseStatus.FAILED,
            EvalCaseStatus.ERROR,
        ]
        assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_privacy_exposure_calculation(self, evaluator):
        """测试隐私暴露度计算"""
        # 不含敏感信息
        exposure1 = evaluator._calculate_privacy_exposure(
            "用户喜欢使用思维导图", "教学经验丰富"
        )
        assert exposure1 == 0.0

        # 包含一个敏感信息
        exposure2 = evaluator._calculate_privacy_exposure(
            "用户电话：13800138000", "教学经验丰富"
        )
        assert exposure2 > 0.0
        assert exposure2 < 1.0

        # 包含多个敏感信息
        exposure3 = evaluator._calculate_privacy_exposure(
            "电话：13800138000，邮箱：test@example.com", "地址：北京市"
        )
        assert exposure3 > exposure2

    @pytest.mark.asyncio
    async def test_assertion_execution_in_evaluation(self, evaluator):
        """测试评估中的断言执行"""
        case = EvalCase(
            case_id="memory_assertion_test_001",
            category="memory_retrieval",
            description="测试断言执行",
            version="1.0",
            input={
                "user_id": "eval_user_001",
                "thread_id": "eval_thread_assertion_001",
                "message": "简单问候",
            },
            context={},
            expectations={},
            assertions=[
                EvalAssertion(
                    type=AssertionType.MEMORY_CHECK,
                    field="profile_memory_context",
                    expected={"type": "profile", "should_exist": False},
                    weight=0.5,
                ),
                EvalAssertion(
                    type=AssertionType.NOT_CONTAINS,
                    field="profile_memory_context",
                    expected=["密码"],
                    weight=0.5,
                ),
            ],
            metadata={},
        )

        result = await evaluator.evaluate(case)

        # 即使执行失败或出错，也应该有断言结果
        assert result is not None
        # 如果状态是 ERROR，assertion_results 可能为空
        # 如果成功执行，应该有对应数量的断言结果
        if result.status != EvalCaseStatus.ERROR:
            assert len(result.assertion_results) == len(case.assertions)

    def test_memory_evaluator_inheritance(self):
        """测试 MemoryEvaluator 继承关系"""
        from backend.tests.evals.evaluators.base import BaseEvaluator

        evaluator = MemoryEvaluator()
        assert isinstance(evaluator, BaseEvaluator)

    @pytest.mark.asyncio
    async def test_evaluation_with_missing_fields(self, evaluator):
        """测试处理缺失字段的评估"""
        # 最小化的输入
        case = EvalCase(
            case_id="memory_minimal_001",
            category="memory_retrieval",
            description="最小化输入",
            version="1.0",
            input={"message": "你好"},
            context={},
            expectations={},
            assertions=[
                EvalAssertion(
                    type=AssertionType.MEMORY_CHECK,
                    field="profile_memory_context",
                    expected={"type": "profile", "should_exist": False},
                    weight=1.0,
                )
            ],
            metadata={},
        )

        result = await evaluator.evaluate(case)

        # 应该能够处理缺失的 user_id 和 thread_id，并使用生成的默认值
        assert result is not None
        assert result.case_id == case.case_id
