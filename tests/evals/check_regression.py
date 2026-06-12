"""回归测试基准检查脚本

该脚本读取最新的评估结果，检查关键指标是否满足回归基准要求。
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class RegressionCheckResult:
    """回归检查结果"""

    def __init__(self):
        self.metrics: Dict[str, Dict] = {}
        self.overall_status = "PASS"
        self.failed_metrics: List[str] = []
        self.warnings: List[str] = []

    def add_metric(self, name: str, actual: float, expected: float, threshold_type: str = ">="):
        """添加指标检查结果"""
        passed = self._check_threshold(actual, expected, threshold_type)
        self.metrics[name] = {
            "actual": actual,
            "expected": expected,
            "threshold_type": threshold_type,
            "passed": passed,
        }
        if not passed:
            self.failed_metrics.append(name)
            self.overall_status = "FAIL"

    def add_warning(self, message: str):
        """添加警告信息"""
        self.warnings.append(message)

    @staticmethod
    def _check_threshold(actual: float, expected: float, threshold_type: str) -> bool:
        """检查阈值"""
        if threshold_type == ">=":
            return actual >= expected
        elif threshold_type == "==":
            return actual == expected
        elif threshold_type == "<=":
            return actual <= expected
        return False


def find_latest_result(results_dir: Path) -> Optional[Path]:
    """找到最新的评估结果文件"""
    if not results_dir.exists():
        return None

    eval_files = list(results_dir.glob("eval_*.json"))
    if not eval_files:
        return None

    # 按修改时间排序，返回最新的
    latest = sorted(eval_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    return latest


def load_eval_result(result_file: Path) -> Optional[Dict]:
    """加载评估结果文件"""
    try:
        with open(result_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load result file: {e}")
        return None


def extract_category_scores(eval_data: Dict) -> Dict[str, float]:
    """从评估数据中提取分类分数"""
    return eval_data.get("category_scores", {})


def extract_pass_rate(eval_data: Dict) -> float:
    """计算总体通过率"""
    total = eval_data.get("total_cases", 0)
    if total == 0:
        return 0.0
    passed = eval_data.get("passed", 0)
    return passed / total


def check_regression(eval_data: Dict) -> RegressionCheckResult:
    """检查回归基准

    关键指标：
    - intent_recognition: 100% 必须通过（CRITICAL）
    - memory_retrieval: ≥80% 通过率（HIGH）
    - extraction_quality: ≥80% 通过率（HIGH）
    """
    result = RegressionCheckResult()

    category_scores = extract_category_scores(eval_data)

    # 检查意图识别（CRITICAL）
    intent_score = category_scores.get("intent_recognition", 0.0)
    result.add_metric(
        "intent_recognition",
        actual=intent_score * 100,
        expected=100.0,
        threshold_type="=="
    )

    # 检查记忆检索（HIGH）
    memory_retrieval_score = category_scores.get("memory_retrieval", 0.0)
    if memory_retrieval_score > 0:
        result.add_metric(
            "memory_retrieval",
            actual=memory_retrieval_score * 100,
            expected=80.0,
            threshold_type=">="
        )
    else:
        result.add_warning("memory_retrieval: 无评估数据（跳过检查）")

    # 检查提取质量（HIGH）
    extraction_score = category_scores.get("extraction_quality", 0.0)
    if extraction_score > 0:
        result.add_metric(
            "extraction_quality",
            actual=extraction_score * 100,
            expected=80.0,
            threshold_type=">="
        )
    else:
        result.add_warning("extraction_quality: 无评估数据（跳过检查）")

    # 检查总体通过率
    overall_pass_rate = extract_pass_rate(eval_data)
    if overall_pass_rate < 0.7:
        result.add_warning(
            f"Overall pass rate is low: {overall_pass_rate*100:.1f}% "
            "(recommendation: investigate failures)"
        )

    return result


def print_regression_report(eval_data: Dict, check_result: RegressionCheckResult):
    """打印回归测试报告"""

    print()
    print("=" * 70)
    print("[REGRESSION] Regression Test Results")
    print("=" * 70)

    # 打印每个指标
    for metric_name, metric_data in check_result.metrics.items():
        status = "PASS" if metric_data["passed"] else "FAIL"
        status_symbol = "✅" if metric_data["passed"] else "❌"

        actual = metric_data["actual"]
        expected = metric_data["expected"]
        threshold_type = metric_data["threshold_type"]

        if threshold_type == "==":
            match_str = f"{actual:.1f}% (expected {expected:.1f}%)"
        else:
            match_str = f"{actual:.1f}% ({threshold_type} {expected:.1f}%)"

        print(f"[{status}] {metric_name:<30} {match_str:<30} {status_symbol}")

    # 打印警告
    if check_result.warnings:
        print()
        print("[WARNINGS]")
        for warning in check_result.warnings:
            print(f"  ⚠️  {warning}")

    # 打印总体状态
    print()
    if check_result.overall_status == "PASS":
        print(f"Overall: PASS ✅")
        print()
    else:
        print(f"Overall: FAIL ❌")
        print()
        print("[FAILED METRICS]")
        for failed_metric in check_result.failed_metrics:
            metric_data = check_result.metrics[failed_metric]
            actual = metric_data["actual"]
            expected = metric_data["expected"]
            print(f"  - {failed_metric}: expected {expected:.1f}%, got {actual:.1f}%")
        print()

    # 打印详细信息
    print("[SUMMARY]")
    print(f"  Total cases: {eval_data.get('total_cases', 0)}")
    print(f"  Passed: {eval_data.get('passed', 0)}")
    print(f"  Failed: {eval_data.get('failed', 0)}")
    print(f"  Error: {eval_data.get('error', 0)}")
    print(f"  Average score: {eval_data.get('avg_score', 0):.3f}")
    print(f"  Execution time: {eval_data.get('execution_time', 0):.2f}s")

    timestamp = eval_data.get('timestamp', 'unknown')
    print(f"  Timestamp: {timestamp}")
    print()


def print_usage_hints():
    """打印使用提示"""
    print()
    print("[HINTS] To run evaluations and check regression:")
    print()
    print("  1. Run full evaluation suite:")
    print("     python -m tests.evals.cli run")
    print()
    print("  2. Check regression baseline:")
    print("     python -m tests.evals.check_regression")
    print()
    print("  3. Run specific category:")
    print("     python -m tests.evals.cli run --category intent_recognition")
    print()


def main():
    """主函数"""

    # 确定结果目录
    evals_dir = Path(__file__).parent
    results_dir = evals_dir / "results"

    # 查找最新结果
    latest_result = find_latest_result(results_dir)

    if not latest_result:
        print()
        print("=" * 70)
        print("[ERROR] No evaluation results found")
        print("=" * 70)
        print()
        print(f"Expected results directory: {results_dir}")
        print()
        print_usage_hints()
        return 1

    # 加载评估结果
    eval_data = load_eval_result(latest_result)

    if not eval_data:
        return 1

    # 检查回归基准
    check_result = check_regression(eval_data)

    # 打印报告
    print_regression_report(eval_data, check_result)

    # 返回适当的 exit code
    exit_code = 0 if check_result.overall_status == "PASS" else 1

    if exit_code == 0:
        print("[SUCCESS] All regression checks passed! ✅")
    else:
        print("[FAILURE] Regression checks failed! ❌")

    print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
