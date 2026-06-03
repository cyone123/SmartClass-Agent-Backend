from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.config import (
    get_observability_enabled,
    get_observability_log_level,
    get_observability_max_field_chars,
    get_observability_max_jsonl_bytes_per_event,
    get_observability_trace_jsonl_dir,
    get_observability_trace_jsonl_enabled,
)

ObservationKind = Literal["log", "span", "metric"]
ObservationStatus = Literal["running", "success", "failed"]
ErrorCategory = Literal[
    "model_error",
    "tool_error",
    "workspace_error",
    "rag_error",
    "artifact_error",
    "memory_error",
    "storage_error",
    "permission_error",
    "validation_error",
    "timeout",
    "unknown",
]

SENSITIVE_KEY_RE = re.compile(
    r"(?i)(^|_|\b)(authorization|access_token|refresh_token|jwt|bearer|password|passwd|"
    r"api[_-]?key|secret|secret[_-]?key|credential|credentials|daytona[_-]?api[_-]?key|"
    r"minio[_-]?(access|secret)[_-]?key)(_|$|\b)"
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
HOST_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s\"']+")
URL_SECRET_PARAMS = {
    "x-amz-credential",
    "x-amz-signature",
    "x-amz-security-token",
    "x-amz-expires",
    "access_token",
    "token",
    "signature",
    "credential",
    "api_key",
    "apikey",
    "secret",
    "password",
}
REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    thread_id: str | None = None
    plan_id: int | None = None
    user_id: str | None = None
    agent_name: str | None = None

    def with_agent(self, agent_name: str | None) -> "RunContext":
        return replace(self, agent_name=agent_name or self.agent_name)


@dataclass(frozen=True)
class ObservationEvent:
    event: str
    kind: ObservationKind
    context: RunContext
    status: ObservationStatus | None = None
    duration_ms: int | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "event": self.event,
            "kind": self.kind,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
            **asdict(self.context),
            **self.fields,
        }
        return {key: value for key, value in payload.items() if value is not None}


class ObservationSink(Protocol):
    def emit(self, event: ObservationEvent) -> None:
        ...


class NoopObservationSink:
    def emit(self, event: ObservationEvent) -> None:
        _ = event


class LoggingObservationSink:
    def __init__(self, *, level: str | None = None) -> None:
        self.logger = logging.getLogger("app.observability")
        self.level = _coerce_log_level(level or get_observability_log_level())

    def emit(self, event: ObservationEvent) -> None:
        payload = _sanitize_event(event).to_dict()
        self.logger.log(self.level, event.event, extra={"observation": payload})


class JsonlTraceSink:
    def __init__(self, *, trace_dir: Path | None = None) -> None:
        self.trace_dir = trace_dir or get_observability_trace_jsonl_dir()
        self.logger = logging.getLogger("app.observability")

    def emit(self, event: ObservationEvent) -> None:
        payload = _jsonl_payload(event)

        path = self.trace_dir / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
        except Exception as exc:  # pragma: no cover - warning-only fallback
            self.logger.warning("observability_jsonl_write_failed", extra={"error": str(exc)})


class CompositeObservationSink:
    def __init__(self, sinks: list[ObservationSink]) -> None:
        self.sinks = sinks
        self.logger = logging.getLogger("app.observability")

    def emit(self, event: ObservationEvent) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                self.logger.warning(
                    "observability_sink_emit_failed",
                    extra={"sink": sink.__class__.__name__, "error": str(exc)},
                )


def get_observation_sink() -> ObservationSink:
    if not get_observability_enabled():
        return NoopObservationSink()

    sinks: list[ObservationSink] = [LoggingObservationSink()]
    if get_observability_trace_jsonl_enabled():
        sinks.append(JsonlTraceSink())
    return CompositeObservationSink(sinks)


def run_context_from_config(config: Any | None, *, default_run_id: str = "adhoc") -> RunContext:
    configurable = _configurable(config)
    return RunContext(
        run_id=str(configurable.get("run_id") or default_run_id),
        thread_id=_optional_str(configurable.get("thread_id")),
        plan_id=_optional_int(configurable.get("plan_id")),
        user_id=_optional_str(configurable.get("user_id")),
        agent_name=_optional_str(configurable.get("agent_name")),
    )


def observation_sink_from_config(config: Any | None) -> ObservationSink:
    configurable = _configurable(config)
    sink = configurable.get("observation_sink")
    if hasattr(sink, "emit") and callable(sink.emit):
        return sink
    return get_observation_sink()


def log_observation(
    event: str,
    *,
    context: RunContext,
    sink: ObservationSink | None = None,
    status: ObservationStatus | None = None,
    fields: Mapping[str, Any] | None = None,
) -> None:
    _safe_emit(
        sink or get_observation_sink(),
        ObservationEvent(
            event=event,
            kind="log",
            context=context,
            status=status,
            fields=sanitize_observation_fields(fields or {}),
        ),
    )


def record_metric(
    event: str,
    *,
    context: RunContext,
    sink: ObservationSink | None = None,
    status: ObservationStatus | None = None,
    duration_ms: int | None = None,
    fields: Mapping[str, Any] | None = None,
) -> None:
    _safe_emit(
        sink or get_observation_sink(),
        ObservationEvent(
            event=event,
            kind="metric",
            context=context,
            status=status,
            duration_ms=duration_ms,
            fields=sanitize_observation_fields(fields or {}),
        ),
    )


@contextmanager
def trace_span(
    event: str,
    *,
    context: RunContext,
    sink: ObservationSink | None = None,
    fields: Mapping[str, Any] | None = None,
    error_category: ErrorCategory | None = None,
):
    target_sink = sink or get_observation_sink()
    base_fields = sanitize_observation_fields(fields or {})
    _safe_emit(
        target_sink,
        ObservationEvent(event=event, kind="span", context=context, status="running", fields=base_fields),
    )
    start = time.perf_counter()
    span_fields = dict(base_fields)
    try:
        yield span_fields
    except BaseException as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        failed_fields = dict(span_fields)
        failed_fields.update(
            {
                "error_category": error_category or categorize_error(exc),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            }
        )
        _safe_emit(
            target_sink,
            ObservationEvent(
                event=event,
                kind="span",
                context=context,
                status="failed",
                duration_ms=duration_ms,
                fields=sanitize_observation_fields(failed_fields),
            ),
        )
        raise
    else:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _safe_emit(
            target_sink,
            ObservationEvent(
                event=event,
                kind="span",
                context=context,
                status="success",
                duration_ms=duration_ms,
                fields=sanitize_observation_fields(span_fields),
            ),
        )


async def observe_llm_call(
    event: str,
    invoke: Callable[[], Awaitable[Any]],
    *,
    context: RunContext,
    sink: ObservationSink | None = None,
    model: Any = None,
    messages: Sequence[Any] | None = None,
    fields: Mapping[str, Any] | None = None,
) -> Any:
    started_at = time.perf_counter()
    base_fields = dict(fields or {})
    target_sink = sink or get_observation_sink()
    try:
        result = await invoke()
    except Exception as exc:
        failed_fields = _llm_observation_fields(
            model=model,
            messages=messages,
            result=None,
            fields=base_fields,
        )
        failed_fields.update(
            {
                "error_category": categorize_error(exc),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            }
        )
        record_metric(
            event,
            context=context,
            sink=target_sink,
            status="failed",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            fields=failed_fields,
        )
        raise

    record_metric(
        event,
        context=context,
        sink=target_sink,
        status="success",
        duration_ms=int((time.perf_counter() - started_at) * 1000),
        fields=_llm_observation_fields(
            model=model,
            messages=messages,
            result=result,
            fields=base_fields,
        ),
    )
    return result


def extract_token_usage(message_or_response: Any) -> dict[str, Any]:
    if message_or_response is None:
        return {"token_usage_available": False}

    usage = getattr(message_or_response, "usage_metadata", None)
    if isinstance(usage, Mapping):
        return _normalize_token_usage(
            usage,
            input_keys=("input_tokens", "prompt_tokens"),
            output_keys=("output_tokens", "completion_tokens"),
            total_keys=("total_tokens",),
        )

    metadata = getattr(message_or_response, "response_metadata", None)
    token_usage = None
    if isinstance(metadata, Mapping):
        token_usage = (
            metadata.get("token_usage")
            or metadata.get("usage")
            or metadata.get("usage_metadata")
        )
    if isinstance(token_usage, Mapping):
        return _normalize_token_usage(
            token_usage,
            input_keys=("input_tokens", "prompt_tokens"),
            output_keys=("output_tokens", "completion_tokens"),
            total_keys=("total_tokens",),
        )

    if isinstance(message_or_response, Mapping):
        for key in ("usage_metadata", "token_usage", "usage"):
            value = message_or_response.get(key)
            if isinstance(value, Mapping):
                return _normalize_token_usage(
                    value,
                    input_keys=("input_tokens", "prompt_tokens"),
                    output_keys=("output_tokens", "completion_tokens"),
                    total_keys=("total_tokens",),
                )
        raw = message_or_response.get("raw")
        if raw is not None:
            raw_usage = extract_token_usage(raw)
            if raw_usage.get("token_usage_available"):
                return raw_usage

    llm_output = getattr(message_or_response, "llm_output", None)
    if isinstance(llm_output, Mapping) and isinstance(llm_output.get("token_usage"), Mapping):
        return _normalize_token_usage(
            llm_output["token_usage"],
            input_keys=("input_tokens", "prompt_tokens"),
            output_keys=("output_tokens", "completion_tokens"),
            total_keys=("total_tokens",),
        )

    result = getattr(message_or_response, "result", None)
    if isinstance(result, list):
        for item in reversed(result):
            item_usage = extract_token_usage(item)
            if item_usage.get("token_usage_available"):
                return item_usage

    return {"token_usage_available": False}


def categorize_error(exc: BaseException) -> ErrorCategory:
    try:
        from app.core.storage import StorageError
        from app.core.workspace import WorkspaceExecutionError, WorkspaceValidationError
    except Exception:  # pragma: no cover - import-cycle guard
        StorageError = WorkspaceExecutionError = WorkspaceValidationError = ()  # type: ignore[assignment]

    if isinstance(exc, TimeoutError):
        return "timeout"
    if StorageError and isinstance(exc, StorageError):
        return "storage_error"
    if WorkspaceValidationError and isinstance(exc, WorkspaceValidationError):
        text = str(exc).lower()
        if "permission" in text or "traversal" in text or "outside" in text:
            return "permission_error"
        return "validation_error"
    if WorkspaceExecutionError and isinstance(exc, WorkspaceExecutionError):
        text = str(exc).lower()
        if "timeout" in text or "timed out" in text:
            return "timeout"
        return "workspace_error"

    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "rag" in name or "vector" in name:
        return "rag_error"
    if "artifact" in name:
        return "artifact_error"
    if "permission" in name or "forbidden" in name:
        return "permission_error"
    if "validation" in name:
        return "validation_error"
    if "timeout" in name or "timed out" in message:
        return "timeout"
    if any(marker in name for marker in ("openai", "llm", "model")):
        return "model_error"
    return "unknown"


def sanitize_observation_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    max_chars = get_observability_max_field_chars()
    return {str(key): _sanitize_value(str(key), value, max_chars=max_chars) for key, value in fields.items()}


def _sanitize_event(event: ObservationEvent) -> ObservationEvent:
    return replace(event, fields=sanitize_observation_fields(event.fields))


def _jsonl_payload(event: ObservationEvent) -> str:
    max_bytes = get_observability_max_jsonl_bytes_per_event()
    sanitized = _sanitize_event(event)
    payload_dict = sanitized.to_dict()
    payload = _json_dumps(payload_dict)
    if _byte_len(payload) <= max_bytes:
        return payload

    compact_fields = _compact_json_fields(dict(sanitized.fields), max_bytes=max(0, max_bytes // 2))
    compact_event = replace(sanitized, fields={**compact_fields, "jsonl_truncated": True})
    payload = _json_dumps(compact_event.to_dict())
    if _byte_len(payload) <= max_bytes:
        return payload

    minimal = ObservationEvent(
        event=sanitized.event,
        kind=sanitized.kind,
        context=sanitized.context,
        status=sanitized.status,
        duration_ms=sanitized.duration_ms,
        created_at=sanitized.created_at,
        fields={"jsonl_truncated": True},
    ).to_dict()
    payload = _json_dumps(minimal)
    if _byte_len(payload) <= max_bytes:
        return payload

    # The event envelope itself is larger than the configured cap. Keep JSON valid;
    # callers rely on line parseability more than on an exact byte limit at this point.
    return payload


def _sanitize_value(key: str, value: Any, *, max_chars: int) -> Any:
    if SENSITIVE_KEY_RE.search(key):
        return REDACTED
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _sanitize_value(str(k), v, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(key, item, max_chars=max_chars) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _sanitize_value(key, value.model_dump(mode="json"), max_chars=max_chars)
    if is_dataclass(value) and not isinstance(value, type):
        return _sanitize_value(key, asdict(value), max_chars=max_chars)
    if isinstance(value, Path):
        return _sanitize_text(str(value), max_chars=max_chars)
    if isinstance(value, str):
        return _sanitize_text(value, max_chars=max_chars)
    return _sanitize_text(str(value), max_chars=max_chars)


def _sanitize_text(text: str, *, max_chars: int) -> str:
    value = BEARER_RE.sub("Bearer " + REDACTED, text)
    value = JWT_RE.sub(REDACTED, value)
    value = HOST_PATH_RE.sub("[REDACTED_PATH]", value)
    value = _sanitize_url_query(value)
    if len(value) > max_chars:
        return f"{value[:max_chars].rstrip()}...[truncated]"
    return value


def _sanitize_url_query(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        parts = urlsplit(raw_url)
        query = []
        changed = False
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower() in URL_SECRET_PARAMS:
                query.append((key, REDACTED))
                changed = True
            else:
                query.append((key, value))
        if not changed:
            return raw_url
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    return re.sub(r"https?://[^\s\"']+", repl, text)


def _safe_emit(sink: ObservationSink, event: ObservationEvent) -> None:
    try:
        sink.emit(_sanitize_event(event))
    except Exception as exc:  # pragma: no cover - warning-only fallback
        logging.getLogger("app.observability").warning(
            "observability_emit_failed",
            extra={"event": event.event, "error": str(exc)},
        )


def _llm_observation_fields(
    *,
    model: Any,
    messages: Sequence[Any] | None,
    result: Any,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    message_list = list(messages or [])
    result_messages = _result_messages(result)
    output_size = sum(len(_message_like_text(message)) for message in result_messages)
    if not result_messages and result is not None:
        output_size = len(_message_like_text(result))
    usage = extract_token_usage(result)
    return {
        "model": _model_name(model),
        "message_count": len(message_list),
        "input_size": sum(len(_message_like_text(message)) for message in message_list),
        "output_size": output_size,
        **fields,
        **usage,
    }


def _result_messages(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return list(result)
    result_attr = getattr(result, "result", None)
    if isinstance(result_attr, list):
        return result_attr
    return [result]


def _message_like_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, Mapping):
                value = part.get("text") or part.get("content")
                if value is not None:
                    pieces.append(str(value))
        return "".join(pieces)
    return str(content or "")


def _model_name(model: Any) -> str:
    if model is None:
        return "unknown"
    for attr in ("model_name", "model", "model_id", "name"):
        value = getattr(model, attr, None)
        if value:
            return str(value)
    return model.__class__.__name__


def _json_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _compact_json_fields(fields: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in sorted(fields):
        if key == "jsonl_truncated":
            continue
        candidate = {**compact, key: _summarize_json_value(fields[key])}
        if _byte_len(_json_dumps(candidate)) > max_bytes:
            compact[f"{key}_omitted"] = True
            break
        compact = candidate
    return compact


def _summarize_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {"type": "object", "keys": sorted(str(key) for key in value.keys())[:20]}
    if isinstance(value, list):
        return {"type": "list", "length": len(value)}
    if isinstance(value, tuple):
        return {"type": "tuple", "length": len(value)}
    if isinstance(value, set):
        return {"type": "set", "length": len(value)}
    if isinstance(value, str):
        return value[:120] + ("...[truncated]" if len(value) > 120 else "")
    return value


def _normalize_token_usage(
    usage: Mapping[str, Any],
    *,
    input_keys: tuple[str, ...],
    output_keys: tuple[str, ...],
    total_keys: tuple[str, ...],
) -> dict[str, Any]:
    input_tokens = _first_int(usage, input_keys)
    output_tokens = _first_int(usage, output_keys)
    total_tokens = _first_int(usage, total_keys)
    result: dict[str, Any] = {"token_usage_available": True}
    if input_tokens is not None:
        result["input_tokens"] = input_tokens
    if output_tokens is not None:
        result["output_tokens"] = output_tokens
    if total_tokens is not None:
        result["total_tokens"] = total_tokens
    return result


def _first_int(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int):
            return value
    return None


def _configurable(config: Any | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    value = config.get("configurable")
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_log_level(value: str | None) -> int:
    normalized = (value or "info").strip().upper()
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }.get(normalized, logging.INFO)
