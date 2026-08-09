"""Pure helpers for parsing and summarizing SSE benchmark samples."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b"
    r"(\s*[:=]\s*)(['\"]?)[^,'\";\s}\]]+\3"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_RE = re.compile(r"https?://[^\s\"']+")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+")
_STRING_FIELD_RE = re.compile(r"['\"](type|code)['\"]\s*:\s*['\"]([^'\"]+)['\"]")


def sse_events(response: Any) -> Iterator[tuple[str, str]]:
    """Yield complete SSE events from a requests/Locust streaming response."""

    event_name = "message"
    data_lines: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="replace")
        else:
            line = str(raw_line)

        if line == "":
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        yield event_name, "\n".join(data_lines)


def nearest_percentile(response_times: dict[int, int], percentile: float) -> float:
    """Return a nearest-rank percentile from Locust's frequency map."""

    total = sum(response_times.values())
    if total <= 0:
        return 0.0
    rank = max(1, math.ceil(total * percentile))
    seen = 0
    for response_time, count in sorted(response_times.items()):
        seen += count
        if seen >= rank:
            return float(response_time)
    return float(max(response_times))


def _redact_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "<url>"
    if not parsed.scheme or not parsed.netloc:
        return "<url>"
    path = parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def sanitize_error_text(value: Any, *, max_chars: int = 240) -> str:
    """Keep a short diagnostic snippet without credentials or local paths."""

    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    else:
        text = str(value or "")
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1\2<redacted>", text)
    text = _URL_RE.sub(_redact_url, text)
    text = _WINDOWS_PATH_RE.sub("<path>", text)
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text or "<empty>"


def classify_error_reason(message: str) -> str:
    """Map provider/backend text to a bounded, low-cardinality reason."""

    lowered = message.lower()
    if any(marker in lowered for marker in ("429", "rate limit", "too many requests", "throttl")):
        return "rate_limit"
    if any(marker in lowered for marker in ("quota", "insufficient balance", "billing", "credit", "402")):
        return "quota_or_billing"
    if any(marker in lowered for marker in ("timeout", "timed out", "read timed out")):
        return "timeout"
    if "response_format" in lowered and any(marker in lowered for marker in ("unavailable", "unsupported")):
        return "unsupported_response_format"
    if any(marker in lowered for marker in ("401", "403", "unauthorized", "forbidden", "api key")):
        return "authentication_or_permission"
    if any(marker in lowered for marker in ("502", "503", "504", "bad gateway", "service unavailable")):
        return "upstream_5xx"
    if any(marker in lowered for marker in ("connection", "connect", "ssl", "dns")):
        return "transport"
    if any(marker in lowered for marker in ("400", "validation", "invalid request", "context length")):
        return "request_validation"
    return "unknown"


def parse_error_reason(data: str) -> dict[str, str]:
    """Extract a bounded diagnostic record from an SSE error payload."""

    payload: Any = None
    try:
        payload = json.loads(data)
    except (TypeError, ValueError):
        pass

    source: Any = payload if isinstance(payload, dict) else {}
    nested_error = source.get("error") if isinstance(source, dict) else None
    if isinstance(nested_error, dict):
        source = {**source, **nested_error}

    message_value = ""
    if isinstance(source, dict):
        for key in ("message", "error_message", "detail", "error"):
            candidate = source.get(key)
            if candidate not in (None, "") and not isinstance(candidate, dict):
                message_value = str(candidate)
                break
    if not message_value:
        message_value = data

    message = sanitize_error_text(message_value)
    category = sanitize_error_text(source.get("error_category"), max_chars=64) if isinstance(source, dict) else ""
    error_type = sanitize_error_text(source.get("error_type"), max_chars=64) if isinstance(source, dict) else ""
    if error_type in ("", "<empty>"):
        match = _STRING_FIELD_RE.search(message_value)
        if match:
            error_type = sanitize_error_text(match.group(2), max_chars=64)
    return {
        "category": category if category != "<empty>" else "unknown",
        "reason": classify_error_reason(message),
        "error_type": error_type if error_type not in ("", "<empty>") else "unknown",
        "message": message,
    }


__all__ = [
    "classify_error_reason",
    "nearest_percentile",
    "parse_error_reason",
    "sanitize_error_text",
    "sse_events",
]
