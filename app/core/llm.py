from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.config import (
    get_context_compression_api_key,
    get_context_compression_base_url,
    get_context_compression_model,
    get_context_compression_timeout_seconds,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _first_non_empty_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _get_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _get_timeout_seconds() -> float | None:
    raw_value = os.getenv("STRUCTURED_TIMEOUT_MS")
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    timeout_ms = int(normalized)
    if timeout_ms <= 0:
        return None
    return timeout_ms / 1000


def _stream_usage_kwargs(streaming: bool) -> dict[str, bool]:
    if not streaming:
        return {}
    return {"stream_usage": True}


def _thinking_mode_kwargs(env_name: str = "MODEL_THINKING_MODE") -> dict[str, object]:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return {}
    mode = raw_value.strip().lower()
    if mode not in {"enabled", "disabled"}:
        raise ValueError(f"{env_name} must be 'enabled' or 'disabled'")
    return {"extra_body": {"thinking": {"type": mode}}}


def _structured_thinking_kwargs(model: str | None, base_url: str | None) -> dict[str, object]:
    """Disable DeepSeek thinking when structured output uses tool calling."""

    provider_text = f"{model or ''} {base_url or ''}".lower()
    if "deepseek" in provider_text:
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}


def get_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        streaming=streaming,
        **_stream_usage_kwargs(streaming),
        **_thinking_mode_kwargs(),
    )


def get_structured_output_model(*, streaming: bool = False) -> ChatOpenAI:
    model = os.getenv("STRUCTED_MDOEL")
    base_url = os.getenv("STRUCTED_BASE_URL")
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("STRUCTED_API_KEY"),
        base_url=base_url,
        streaming=streaming,
        timeout=_get_timeout_seconds(),
        **_stream_usage_kwargs(streaming),
        **_structured_thinking_kwargs(model, base_url),
    )


def get_small_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("SMALL_MDOEL"),
        api_key=os.getenv("SMALL_API_KEY"),
        base_url=os.getenv("SMALL_BASE_URL"),
        streaming=streaming,
        **_stream_usage_kwargs(streaming),
    )


def get_memory_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=_first_non_empty_env(
            "MEMORY_MODEL",
            "STRUCTURED_FAST_MODEL",
            "STRUCTED_MDOEL",
            "SMALL_MDOEL",
            "MODEL",
        ),
        api_key=_first_non_empty_env(
            "MEMORY_API_KEY",
            "STRUCTURED_FAST_API_KEY",
            "SMALL_API_KEY",
            "STRUCTED_API_KEY",
            "API_KEY",
        ),
        base_url=_first_non_empty_env(
            "MEMORY_BASE_URL",
            "STRUCTURED_FAST_BASE_URL",
            "SMALL_BASE_URL",
            "STRUCTED_BASE_URL",
            "BASE_URL",
        ),
        streaming=streaming,
        timeout=_get_timeout_seconds(),
        **_stream_usage_kwargs(streaming),
    )


def get_context_compression_llm(*, streaming: bool = False) -> ChatOpenAI:
    """Return the dedicated short-term context compression model.

    Explicit CONTEXT_COMPRESSION_* values win. When omitted, fall back to the
    existing memory/structured/small/main model chain so deployments can enable
    compression before provisioning a separate model endpoint.
    """
    return ChatOpenAI(
        model=(
            get_context_compression_model()
            or _first_non_empty_env(
                "MEMORY_MODEL",
                "STRUCTURED_FAST_MODEL",
                "STRUCTED_MDOEL",
                "SMALL_MDOEL",
                "MODEL",
            )
        ),
        api_key=(
            get_context_compression_api_key()
            or _first_non_empty_env(
                "MEMORY_API_KEY",
                "STRUCTURED_FAST_API_KEY",
                "STRUCTED_API_KEY",
                "STRUCTURED_API_KEY",
                "SMALL_API_KEY",
                "API_KEY",
            )
        ),
        base_url=(
            get_context_compression_base_url()
            or _first_non_empty_env(
                "MEMORY_BASE_URL",
                "STRUCTURED_FAST_BASE_URL",
                "STRUCTED_BASE_URL",
                "SMALL_BASE_URL",
                "BASE_URL",
            )
        ),
        streaming=streaming,
        timeout=get_context_compression_timeout_seconds() or _get_timeout_seconds(),
        **_stream_usage_kwargs(streaming),
    )


def get_structured_fast_model(*, streaming: bool = False) -> ChatOpenAI:
    model = _first_non_empty_env("STRUCTURED_FAST_MODEL", "SMALL_MDOEL")
    base_url = _first_non_empty_env("STRUCTURED_FAST_BASE_URL", "SMALL_BASE_URL")
    return ChatOpenAI(
        model=model,
        api_key=_first_non_empty_env("STRUCTURED_FAST_API_KEY", "SMALL_API_KEY"),
        base_url=base_url,
        streaming=streaming,
        timeout=_get_timeout_seconds(),
        **_stream_usage_kwargs(streaming),
        **_structured_thinking_kwargs(model, base_url),
    )


def is_structured_fallback_enabled() -> bool:
    return _get_bool_env("STRUCTURED_FALLBACK_ENABLED", True)


def is_structured_warmup_enabled() -> bool:
    return _get_bool_env("STRUCTURED_WARMUP_ENABLED", True)


def is_structured_prompt_cache_enabled() -> bool:
    return _get_bool_env("STRUCTURED_PROMPT_CACHE_ENABLED", False)


def get_structured_prompt_cache_retention() -> str | None:
    retention = os.getenv("STRUCTURED_PROMPT_CACHE_RETENTION")
    if retention is None:
        return None
    normalized = retention.strip()
    return normalized or None


llm = get_model(streaming=True)
structured_fast_llm = get_structured_fast_model(streaming=False)
structured_output_llm = get_structured_output_model(streaming=False)
memory_llm = get_memory_model(streaming=False)
