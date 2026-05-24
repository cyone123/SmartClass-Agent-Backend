from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

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


def get_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        streaming=streaming,
    )


def get_structured_output_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("STRUCTED_MDOEL"),
        api_key=os.getenv("STRUCTED_API_KEY"),
        base_url=os.getenv("STRUCTED_BASE_URL"),
        streaming=streaming,
        timeout=_get_timeout_seconds(),
    )


def get_small_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("SMALL_MDOEL"),
        api_key=os.getenv("SMALL_API_KEY"),
        base_url=os.getenv("SMALL_BASE_URL"),
        streaming=streaming,
    )

def get_suggestion_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("SUGGESTION_MODEL"),
        api_key=os.getenv("SUGGESTION_API_KEY"),
        base_url=os.getenv("SUGGESTION_BASE_URL"),
        streaming=streaming,
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
    )


def get_structured_fast_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=_first_non_empty_env("STRUCTURED_FAST_MODEL", "SMALL_MDOEL", "STRUCTED_MDOEL"),
        api_key=_first_non_empty_env("STRUCTURED_FAST_API_KEY", "SMALL_API_KEY", "STRUCTED_API_KEY"),
        base_url=_first_non_empty_env("STRUCTURED_FAST_BASE_URL", "SMALL_BASE_URL", "STRUCTED_BASE_URL"),
        streaming=streaming,
        timeout=_get_timeout_seconds(),
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
