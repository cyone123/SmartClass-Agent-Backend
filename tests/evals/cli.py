"""评估 CLI 工具"""
import os
import sys

# 评估环境配置（必须在导入之前）
os.environ.setdefault("PROMETHEUS_ENABLED", "false")
os.environ.setdefault("OBSERVABILITY_ENABLED", "false")

import asyncio
from pathlib import Path

import click

from .runners import EvalRunner

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    # 修复 Windows asyncio 事件循环问题
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


@click.group()
def cli():
    """SmartClass Evaluation CLI"""
    pass


@cli.command()
def list_categories():
    """List all available evaluation categories"""
    base_dir = Path(__file__).parent
    cases_dir = base_dir / "cases"
    results_dir = base_dir / "results"

    runner = EvalRunner(cases_dir, results_dir)

    categories = {
        "intent_recognition": "意图识别评估（Phase 1）",
        "memory_retrieval": "记忆检索评估（Phase 2）",
        "memory_write": "记忆写入评估（Phase 2）",
        "memory_update": "记忆更新评估（Phase 2）",
        "extraction_quality": "教学要素抽取评估（Phase 2）",
    }

    print(f"\n{'=' * 60}")
    print(f"[CATEGORIES] Available Evaluation Categories:")
    print(f"{'=' * 60}")

    for cat_key, cat_desc in categories.items():
        # Try to count cases for this category
        cases = runner.load_cases(category=cat_key)
        case_count = len(cases)
        count_str = f" ({case_count} case{'s' if case_count != 1 else ''})" if case_count > 0 else ""
        print(f"  {cat_key:<24} - {cat_desc}{count_str}")

    print()


@cli.command()
@click.option("--category", "-c", help="Filter by category (e.g., intent_recognition, memory_retrieval, memory_write, memory_update, extraction_quality)")
@click.option("--case-id", "-i", multiple=True, help="Specific case IDs")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def run(category, case_id, verbose):
    """Run evaluation suite"""
    base_dir = Path(__file__).parent
    cases_dir = base_dir / "cases"
    results_dir = base_dir / "results"

    runner = EvalRunner(cases_dir, results_dir)
    report = asyncio.run(
        runner.run_suite(category=category, case_ids=list(case_id) if case_id else None)
    )

    print(f"\n{'=' * 60}")
    print(f"[REPORT] Evaluation Report")
    print(f"{'=' * 60}")
    print(f"Total: {report.total_cases}")
    if report.total_cases > 0:
        print(f"Passed: {report.passed} ({report.passed/report.total_cases*100:.1f}%)")
        print(f"Failed: {report.failed} ({report.failed/report.total_cases*100:.1f}%)")
    else:
        print(f"Passed: {report.passed}")
        print(f"Failed: {report.failed}")
    print(f"Error: {report.error}")
    print(f"Avg Score: {report.avg_score:.3f}")
    print(f"Execution Time: {report.execution_time:.2f}s")

    if report.category_scores:
        print(f"\n[SCORES] Category Scores:")
        for cat, score in report.category_scores.items():
            print(f"  {cat}: {score:.3f}")

    if verbose and report.results:
        print(f"\n[DETAILS] Detailed Results:")
        for result in report.results:
            print(f"\n  [{result.case_id}]")
            print(f"    Status: {result.status.value}")
            print(f"    Score: {result.score:.3f}")
            if result.error_message:
                print(f"    Error: {result.error_message}")


@cli.command()
@click.argument("case_file", type=click.Path(exists=True))
def validate(case_file):
    """Validate evaluation case file"""
    import yaml

    from app.core.evaluation import EvalCase

    try:
        with open(case_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        case = EvalCase(**data)
        print(f"[OK] Case '{case.case_id}' is valid")
        print(f"   Category: {case.category}")
        print(f"   Description: {case.description}")
        print(f"   Assertions: {len(case.assertions)}")
    except Exception as e:
        print(f"[ERROR] Validation failed: {e}")
        raise click.Abort()


if __name__ == "__main__":
    cli()
