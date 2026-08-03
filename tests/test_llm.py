from __future__ import annotations

import pytest

from app.core.llm import get_model


def _configure_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL", "deepseek/deepseek-v4-flash")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("BASE_URL", "https://example.com/v1")


def test_get_model_can_disable_thinking_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_model(monkeypatch)
    monkeypatch.setenv("MODEL_THINKING_MODE", "disabled")

    model = get_model(streaming=False)

    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_get_model_leaves_thinking_unset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_model(monkeypatch)
    monkeypatch.delenv("MODEL_THINKING_MODE", raising=False)

    model = get_model(streaming=False)

    assert model.extra_body is None


def test_get_model_rejects_invalid_thinking_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_model(monkeypatch)
    monkeypatch.setenv("MODEL_THINKING_MODE", "sometimes")

    with pytest.raises(ValueError, match="MODEL_THINKING_MODE"):
        get_model(streaming=False)
