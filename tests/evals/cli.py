"""评估 CLI 工具"""

import os
import sys

# 评估环境配置（必须在导入之前）
os.environ.setdefault("PROMETHEUS_ENABLED", "false")
os.environ.setdefault("OBSERVABILITY_ENABLED", "false")

import asyncio
from pathlib import Path

import click
from dotenv import dotenv_values

from .reporting import BaselinePromotionError, default_benchmarks_root, promote_baseline
from .suite_validation import format_audit, validate_suite

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    # 修复 Windows asyncio 事件循环问题
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@click.group()
def cli():
    """SmartClass Evaluation CLI"""
    pass


def configure_local_docker_database(env_file: Path) -> None:
    """Point a host-side eval process at the Compose PostgreSQL port."""
    values = dotenv_values(env_file)
    mapping = {
        "DB_PORT": "POSTGRES_PORT",
        "DB_USER": "POSTGRES_USER",
        "DB_PASSWORD": "POSTGRES_PASSWORD",
        "DB_NAME": "POSTGRES_DB",
    }
    missing = [source for source in mapping.values() if not values.get(source)]
    if missing:
        raise click.ClickException(f"Missing Docker database settings: {', '.join(missing)}")
    os.environ["DB_HOST"] = "127.0.0.1"
    for target, source in mapping.items():
        os.environ[target] = str(values[source])


@cli.command()
def list_categories():
    """List all available evaluation categories"""
    from .runners import EvalRunner

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
        "context_compression": "上下文压缩评估",
    }

    print(f"\n{'=' * 60}")
    print("[CATEGORIES] Available Evaluation Categories:")
    print(f"{'=' * 60}")

    for cat_key, cat_desc in categories.items():
        # Try to count cases for this category
        cases = runner.load_cases(category=cat_key)
        case_count = len(cases)
        count_str = f" ({case_count} case{'s' if case_count != 1 else ''})" if case_count > 0 else ""
        print(f"  {cat_key:<24} - {cat_desc}{count_str}")

    print()


@cli.command("validate-suite")
@click.option("--expected-count", type=int, default=None, help="Fail unless this many YAML cases are present")
def validate_suite_command(expected_count):
    """Strictly validate every evaluation case without invoking a model."""
    cases_dir = Path(__file__).parent / "cases"
    result = validate_suite(cases_dir, expected_count=expected_count)
    print(format_audit(result))
    if not result.valid:
        raise click.ClickException("Evaluation suite validation failed")
    print("[OK] Evaluation suite is valid")


@cli.command("promote-baseline")
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--baseline-id", required=True)
@click.option("--benchmarks-root", type=click.Path(path_type=Path), default=None)
@click.option("--replace", is_flag=True, help="Explicitly replace an existing baseline")
def promote_baseline_command(report_path, baseline_id, benchmarks_root, replace):
    """Promote one passing report into sanitized, commit-safe evidence."""
    try:
        target = promote_baseline(
            report_path,
            baseline_id=baseline_id,
            benchmarks_root=benchmarks_root or default_benchmarks_root(),
            replace=replace,
        )
    except BaselinePromotionError as exc:
        raise click.ClickException(str(exc)) from exc
    print(f"[SAVED] Baseline evidence: {target}")


@cli.command()
@click.option(
    "--category",
    "-c",
    help="Filter by category (e.g., intent_recognition, memory_retrieval, memory_write, memory_update, extraction_quality, context_compression)",
)
@click.option("--case-id", "-i", multiple=True, help="Specific case IDs")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option(
    "--local-docker-db",
    is_flag=True,
    help="Use PostgreSQL credentials from the repository .env.docker via 127.0.0.1",
)
def run(category, case_id, verbose, local_docker_db):
    """Run evaluation suite"""
    if local_docker_db:
        configure_local_docker_database(Path(__file__).resolve().parents[3] / ".env.docker")

    from .runners import EvalRunner

    base_dir = Path(__file__).parent
    cases_dir = base_dir / "cases"
    results_dir = base_dir / "results"

    command_args = []
    if category:
        command_args.extend(["--category", category])
    for selected_case_id in case_id:
        command_args.extend(["--case-id", selected_case_id])
    if local_docker_db:
        command_args.append("--local-docker-db")

    runner = EvalRunner(cases_dir, results_dir, command_args=command_args)
    report = asyncio.run(runner.run_suite(category=category, case_ids=list(case_id) if case_id else None))

    print(f"\n{'=' * 60}")
    print("[REPORT] Evaluation Report")
    print(f"{'=' * 60}")
    print(f"Total: {report.total_cases}")
    if report.total_cases > 0:
        print(f"Passed: {report.passed} ({report.passed / report.total_cases * 100:.1f}%)")
        print(f"Failed: {report.failed} ({report.failed / report.total_cases * 100:.1f}%)")
    else:
        print(f"Passed: {report.passed}")
        print(f"Failed: {report.failed}")
    print(f"Error: {report.error}")
    print(f"Avg Score: {report.avg_score:.3f}")
    print(f"Execution Time: {report.execution_time:.2f}s")

    if report.category_scores:
        print("\n[SCORES] Category Scores:")
        for cat, score in report.category_scores.items():
            print(f"  {cat}: {score:.3f}")

    if verbose and report.results:
        print("\n[DETAILS] Detailed Results:")
        for result in report.results:
            print(f"\n  [{result.case_id}]")
            print(f"    Status: {result.status.value}")
            print(f"    Score: {result.score:.3f}")
            if result.error_message:
                print(f"    Error: {result.error_message}")
    if report.error:
        raise click.ClickException(f"Evaluation completed with {report.error} runtime error(s)")


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
