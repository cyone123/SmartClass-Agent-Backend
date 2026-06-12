"""评估运行器集成测试"""
import pytest
from pathlib import Path

from tests.evals.runners import EvalRunner
from tests.evals.evaluators import (
    IntentEvaluator,
    MemoryEvaluator,
    ExtractionEvaluator,
    BaseEvaluator,
)


class TestEvalRunner:
    """评估运行器测试"""

    @pytest.fixture
    def eval_runner(self, tmp_path):
        """创建评估运行器实例"""
        cases_dir = tmp_path / "cases"
        results_dir = tmp_path / "results"
        cases_dir.mkdir()
        results_dir.mkdir()
        return EvalRunner(cases_dir, results_dir)

    def test_eval_runner_loads_all_categories(self, eval_runner):
        """验证所有评估器都已注册"""
        expected_categories = {
            "intent_recognition",
            "memory_retrieval",
            "memory_write",
            "memory_update",
            "extraction_quality",
        }

        actual_categories = set(eval_runner.evaluators.keys())

        assert (
            actual_categories == expected_categories
        ), f"Expected {expected_categories}, got {actual_categories}"

    def test_eval_runner_evaluators_are_correct_types(self, eval_runner):
        """验证评估器类型正确"""
        # intent_recognition should be IntentEvaluator
        assert isinstance(
            eval_runner.evaluators["intent_recognition"], IntentEvaluator
        ), "intent_recognition should be IntentEvaluator"

        # memory_* should all be MemoryEvaluator
        assert isinstance(
            eval_runner.evaluators["memory_retrieval"], MemoryEvaluator
        ), "memory_retrieval should be MemoryEvaluator"
        assert isinstance(
            eval_runner.evaluators["memory_write"], MemoryEvaluator
        ), "memory_write should be MemoryEvaluator"
        assert isinstance(
            eval_runner.evaluators["memory_update"], MemoryEvaluator
        ), "memory_update should be MemoryEvaluator"

        # extraction_quality should be ExtractionEvaluator
        assert isinstance(
            eval_runner.evaluators["extraction_quality"], ExtractionEvaluator
        ), "extraction_quality should be ExtractionEvaluator"

        # All should be BaseEvaluator
        for category, evaluator in eval_runner.evaluators.items():
            assert isinstance(
                evaluator, BaseEvaluator
            ), f"{category} evaluator should be instance of BaseEvaluator"

    def test_eval_runner_loads_cases_by_category(self, eval_runner, tmp_path):
        """验证可以按类别加载用例"""
        # Create sample case files in different categories
        intent_dir = eval_runner.cases_dir / "intent_recognition"
        intent_dir.mkdir()

        memory_dir = eval_runner.cases_dir / "memory_retrieval"
        memory_dir.mkdir()

        extraction_dir = eval_runner.cases_dir / "extraction_quality"
        extraction_dir.mkdir()

        # Create test case files
        intent_case = """case_id: intent_001
category: intent_recognition
description: Test intent recognition
version: "1.0"
input:
  message: "你好"
  user_id: "test_user"
context:
  plan_id: "test_plan"
expectations:
  route: "chat"
assertions:
  - type: route_match
    field: route
    expected: chat
    weight: 1.0
metadata:
  author: "test"
  tags: []
"""

        memory_case = """case_id: memory_001
category: memory_retrieval
description: Test memory retrieval
version: "1.0"
input:
  message: "你好"
  user_id: "test_user"
context:
  plan_id: "test_plan"
expectations:
  profile_memory_context: "test"
assertions:
  - type: memory_check
    field: profile_memory_context
    expected:
      type: profile
      should_exist: true
    weight: 1.0
metadata:
  author: "test"
  tags: []
"""

        extraction_case = """case_id: extraction_001
category: extraction_quality
description: Test extraction quality
version: "1.0"
input:
  message: "你好"
  user_id: "test_user"
context:
  plan_id: "test_plan"
expectations:
  extracted_elements: {}
assertions:
  - type: contains
    field: extracted_elements
    expected: test
    weight: 1.0
metadata:
  author: "test"
  tags: []
"""

        # Write test files
        (intent_dir / "intent_001.yaml").write_text(intent_case, encoding="utf-8")
        (memory_dir / "memory_001.yaml").write_text(memory_case, encoding="utf-8")
        (extraction_dir / "extraction_001.yaml").write_text(
            extraction_case, encoding="utf-8"
        )

        # Test loading by category
        intent_cases = eval_runner.load_cases(category="intent_recognition")
        assert len(intent_cases) == 1, "Should load 1 intent_recognition case"
        assert intent_cases[0].case_id == "intent_001"

        memory_cases = eval_runner.load_cases(category="memory_retrieval")
        assert len(memory_cases) == 1, "Should load 1 memory_retrieval case"
        assert memory_cases[0].case_id == "memory_001"

        extraction_cases = eval_runner.load_cases(category="extraction_quality")
        assert len(extraction_cases) == 1, "Should load 1 extraction_quality case"
        assert extraction_cases[0].case_id == "extraction_001"

        # Test loading all cases
        all_cases = eval_runner.load_cases()
        assert len(all_cases) == 3, "Should load all 3 cases when no category specified"

    def test_eval_runner_category_evaluator_lookup(self, eval_runner):
        """验证评估器查找逻辑"""
        # Verify that each category can find its evaluator
        for category in eval_runner.evaluators.keys():
            evaluator = eval_runner.evaluators.get(category)
            assert evaluator is not None, f"Evaluator for {category} should not be None"
            assert isinstance(evaluator, BaseEvaluator)
