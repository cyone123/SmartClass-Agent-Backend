from __future__ import annotations

from tests.evals.manifest import model_summary_from_environment


def test_model_summary_records_roles_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("MODEL", "main-model")
    monkeypatch.setenv("STRUCTED_MDOEL", "structured-model")
    monkeypatch.setenv("SMALL_MDOEL", "small-model")
    monkeypatch.setenv("STRUCTURED_FAST_MODEL", "fast-model")
    monkeypatch.setenv("API_KEY", "must-not-appear")
    monkeypatch.setenv("SMALL_API_KEY", "also-secret")

    summary = model_summary_from_environment()

    assert summary == {
        "provider": "dashscope",
        "model": "main-model",
        "models": {
            "main": "main-model",
            "structured": "structured-model",
            "fast": "fast-model",
            "small": "small-model",
            "memory": "fast-model",
        },
    }
    assert "must-not-appear" not in str(summary)
    assert "also-secret" not in str(summary)
