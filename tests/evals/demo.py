#!/usr/bin/env python
"""快速演示评估系统的使用"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.evals.cli import cli


def demo():
    """演示评估系统"""
    print("=" * 70)
    print("SmartClass Agent 评估系统演示")
    print("=" * 70)

    print("\n📁 评估系统结构:")
    print("  tests/evals/")
    print("  ├── cases/intent/        # 5个意图识别用例")
    print("  ├── evaluators/          # 评估器（base + intent）")
    print("  ├── runners/             # 运行器")
    print("  ├── rubrics/             # 评分标准")
    print("  └── results/             # 评估结果")

    print("\n📝 可用命令:")
    print("  1. 验证单个用例:")
    print("     python -m tests.evals.cli validate tests/evals/cases/intent/basic_chat.yaml")
    print()
    print("  2. 运行所有评估:")
    print("     python -m tests.evals.cli run")
    print()
    print("  3. 运行意图识别评估:")
    print("     python -m tests.evals.cli run --category intent")
    print()
    print("  4. 运行特定用例:")
    print("     python -m tests.evals.cli run --case-id intent_basic_chat_001")
    print()
    print("  5. 详细输出:")
    print("     python -m tests.evals.cli run --verbose")

    print("\n✅ 已实现 5 个意图识别基准用例:")
    cases = [
        "intent_basic_chat_001       - 基础闲聊意图识别",
        "intent_teaching_plan_001    - 教学规划意图识别",
        "intent_artifact_revision_001 - 产物修改意图识别",
        "intent_ambiguous_001        - 模糊请求处理",
        "intent_mixed_001            - 混合意图识别"
    ]
    for case in cases:
        print(f"  • {case}")

    print("\n⚙️  断言类型:")
    assertions = [
        "route_match      - 路由匹配检查",
        "contains         - 包含检查",
        "not_contains     - 不包含检查",
        "response_quality - LLM评判响应质量"
    ]
    for assertion in assertions:
        print(f"  • {assertion}")

    print("\n" + "=" * 70)
    print("Phase 1 完成！准备运行评估...")
    print("=" * 70)
    print()


if __name__ == "__main__":
    demo()

    # 询问是否运行演示
    print("是否立即验证所有用例格式？(y/n): ", end="")
    choice = input().strip().lower()

    if choice == "y":
        print("\n开始验证用例格式...\n")
        cases_dir = Path(__file__).parent / "cases" / "intent"
        for case_file in sorted(cases_dir.glob("*.yaml")):
            print(f"验证: {case_file.name}")
            sys.argv = ["demo.py", "validate", str(case_file)]
            try:
                cli()
            except SystemExit:
                pass
        print("\n✓ 所有用例格式验证完成！")
    else:
        print("\n提示: 运行 'python -m tests.evals.cli run --category intent' 来执行评估")
