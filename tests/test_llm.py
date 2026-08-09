from __future__ import annotations

import pytest

from app.core.llm import get_model, get_structured_fast_model, get_structured_output_model


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


def test_structured_models_disable_deepseek_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRUCTURED_FAST_MODEL", raising=False)
    monkeypatch.delenv("STRUCTURED_FAST_API_KEY", raising=False)
    monkeypatch.delenv("STRUCTURED_FAST_BASE_URL", raising=False)
    monkeypatch.setenv("STRUCTED_MDOEL", "deepseek-v4-flash")
    monkeypatch.setenv("STRUCTED_API_KEY", "test-key")
    monkeypatch.setenv("STRUCTED_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SMALL_MDOEL", "deepseek-v4-flash")
    monkeypatch.setenv("SMALL_API_KEY", "test-key")
    monkeypatch.setenv("SMALL_BASE_URL", "https://api.deepseek.com")

    structured = get_structured_output_model(streaming=False)
    fast = get_structured_fast_model(streaming=False)

    expected = {"thinking": {"type": "disabled"}}
    assert structured.extra_body == expected
    assert fast.extra_body == expected


def test_structured_models_leave_non_deepseek_thinking_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRUCTURED_FAST_MODEL", raising=False)
    monkeypatch.delenv("STRUCTURED_FAST_API_KEY", raising=False)
    monkeypatch.delenv("STRUCTURED_FAST_BASE_URL", raising=False)
    monkeypatch.setenv("STRUCTED_MDOEL", "qwen-structured")
    monkeypatch.setenv("STRUCTED_API_KEY", "test-key")
    monkeypatch.setenv("STRUCTED_BASE_URL", "https://dashscope.example.com/v1")
    monkeypatch.setenv("SMALL_MDOEL", "qwen-fast")
    monkeypatch.setenv("SMALL_API_KEY", "test-key")
    monkeypatch.setenv("SMALL_BASE_URL", "https://dashscope.example.com/v1")

    structured = get_structured_output_model(streaming=False)
    fast = get_structured_fast_model(streaming=False)

    assert structured.extra_body is None
    assert fast.extra_body is None
