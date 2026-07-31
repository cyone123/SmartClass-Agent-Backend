from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from tests.evals import runners
from tests.evals.cli import cli, configure_local_docker_database


def test_configure_local_docker_database_uses_loopback_and_never_logs_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env.docker"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PORT=15432",
                "POSTGRES_USER=eval-user",
                "POSTGRES_PASSWORD=eval-secret",
                "POSTGRES_DB=eval-db",
            ]
        ),
        encoding="utf-8",
    )
    for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.delenv(key, raising=False)

    configure_local_docker_database(env_file)

    assert os.environ["DB_HOST"] == "127.0.0.1"
    assert os.environ["DB_PORT"] == "15432"
    assert os.environ["DB_USER"] == "eval-user"
    assert os.environ["DB_PASSWORD"] == "eval-secret"
    assert os.environ["DB_NAME"] == "eval-db"


def test_run_command_returns_nonzero_after_saving_runtime_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class ErrorRunner:
        def __init__(self, *args, **kwargs):
            pass

        async def run_suite(self, **kwargs):
            return SimpleNamespace(
                total_cases=1,
                passed=0,
                failed=0,
                error=1,
                avg_score=0.0,
                execution_time=0.1,
                category_scores={"intent_recognition": 0.0},
                results=[],
            )

    monkeypatch.setattr(runners, "EvalRunner", ErrorRunner)
    result = CliRunner().invoke(cli, ["run"])

    assert result.exit_code != 0
    assert "1 runtime error" in result.output
