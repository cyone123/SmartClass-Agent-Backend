"""Locust workload for the non-RAG SSE chat-stream benchmark.

The workload intentionally uses a short normal-chat prompt so that the run
measures the authenticated chat stream and its orchestration overhead without
entering the teaching-plan/RAG/artifact branches.

Authentication is setup-only.  The measured request is the SSE stream itself,
and the script emits a second Locust metric for time-to-first-token (TTFT).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from locust import HttpUser, between, events, task
from locust.env import Environment
from locust.exception import StopUser
from requests import Session

from tests.benchmarks.sse_protocol import nearest_percentile, parse_error_reason, sse_events

PROMPT = os.getenv(
    "SMARTCLASS_BENCHMARK_PROMPT",
    "你好，请用一句中文短句回复：本次非 RAG SSE 压测请求已收到。",
)
READ_TIMEOUT_SECONDS = float(os.getenv("SMARTCLASS_BENCHMARK_READ_TIMEOUT_SECONDS", "180"))
CONNECT_TIMEOUT_SECONDS = float(os.getenv("SMARTCLASS_BENCHMARK_CONNECT_TIMEOUT_SECONDS", "10"))
SETUP_PREFIX = "[setup]"
STREAM_NAME = "/api/chat/stream"
TTFT_NAME = "/api/chat/stream:ttft"
MAX_ERROR_REASONS = 32
ERROR_REASON_COUNTS: Counter[str] = Counter()
ERROR_REASON_SAMPLES: dict[str, dict[str, str]] = {}


def _json_data(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _entry_summary(entry: Any) -> dict[str, Any]:
    requests = int(getattr(entry, "num_requests", 0) or 0)
    failures = int(getattr(entry, "num_failures", 0) or 0)
    response_times = dict(getattr(entry, "response_times", {}) or {})
    return {
        "requests": requests,
        "failures": failures,
        "failure_rate_pct": round(100 * failures / requests, 2) if requests else 0.0,
        "response_time_ms": {
            "p50": round(nearest_percentile(response_times, 0.50), 2),
            "p95": round(nearest_percentile(response_times, 0.95), 2),
            "max": round(float(max(response_times)), 2) if response_times else 0.0,
        },
        "response_length": int(getattr(entry, "total_content_length", 0) or 0),
    }


def _safe_output_path() -> Path | None:
    configured = os.getenv("SMARTCLASS_BENCHMARK_OUTPUT")
    if not configured:
        return None
    path = Path(configured).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _record_error_reason(data: str) -> dict[str, str]:
    detail = parse_error_reason(data)
    signature = "|".join(
        (detail["category"], detail["reason"], detail["error_type"], detail["message"])
    )
    if signature not in ERROR_REASON_COUNTS and len(ERROR_REASON_COUNTS) >= MAX_ERROR_REASONS:
        signature = "unknown|unknown|unknown|<additional reasons redacted>"
        detail = {
            "category": "unknown",
            "reason": "unknown",
            "error_type": "unknown",
            "message": "<additional reasons redacted>",
        }
    ERROR_REASON_COUNTS[signature] += 1
    ERROR_REASON_SAMPLES.setdefault(signature, detail)
    return detail


def _error_reason_summary() -> list[dict[str, Any]]:
    rows = []
    for signature, count in sorted(ERROR_REASON_COUNTS.items(), key=lambda item: (-item[1], item[0])):
        rows.append({"count": count, **ERROR_REASON_SAMPLES[signature]})
    return rows


@events.test_start.add_listener
def reset_error_reasons(**_: Any) -> None:
    ERROR_REASON_COUNTS.clear()
    ERROR_REASON_SAMPLES.clear()


@events.test_stop.add_listener
def write_summary(environment: Environment, **_: Any) -> None:
    """Write an aggregate, secret-free summary when Locust stops."""

    output_path = _safe_output_path()
    if output_path is None or environment.runner is None:
        return

    entries: dict[str, Any] = {}
    for (method, name), entry in environment.stats.entries.items():
        if name.startswith(SETUP_PREFIX):
            continue
        entries[f"{method} {name}"] = _entry_summary(entry)

    total = environment.stats.total
    payload = {
        "schema_version": "1.0",
        "benchmark": "sse-chat-load",
        "run_mode": "live-http-sse",
        "timestamp": datetime.now(UTC).isoformat(),
        "host": environment.host,
        "prompt_mode": "fixed-normal-chat-no-rag",
        "python": sys.version.split()[0],
        "platform": platform.platform(aliased=True),
        "settings": {
            "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
            "read_timeout_seconds": READ_TIMEOUT_SECONDS,
            "users": int(getattr(environment.parsed_options, "num_users", 0) or 0),
            "spawn_rate": float(getattr(environment.parsed_options, "spawn_rate", 0) or 0),
        },
        "metrics": entries,
        "total": _entry_summary(total),
        "error_reasons": _error_reason_summary(),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SmartClassSSEUser(HttpUser):
    """Authenticated normal-chat user for SSE capacity measurements."""

    wait_time = between(0.1, 0.3)

    def on_start(self) -> None:
        self.http = Session()
        self.token = os.getenv("SMARTCLASS_BENCHMARK_TOKEN", "").strip()
        if not self.token:
            self.token = self._login()
        if not self.token:
            raise StopUser()

    def on_stop(self) -> None:
        self.http.close()

    def _login(self) -> str:
        username = os.getenv("SMARTCLASS_BENCHMARK_USERNAME", "").strip()
        password = os.getenv("SMARTCLASS_BENCHMARK_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "Set SMARTCLASS_BENCHMARK_TOKEN or SMARTCLASS_BENCHMARK_USERNAME/"
                "SMARTCLASS_BENCHMARK_PASSWORD before starting the load test."
            )

        with self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            name=f"{SETUP_PREFIX}/api/auth/login",
            catch_response=True,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        ) as response:
            if response.status_code != 200:
                response.failure(f"login status={response.status_code}")
                return ""
            token = str(_json_data(response).get("access_token") or "").strip()
            if not token:
                response.failure("login response did not contain access_token")
            else:
                response.success()
            return token

    @task
    def chat_stream(self) -> None:
        started = time.perf_counter()
        first_token_at: float | None = None
        metadata_seen = False
        token_seen = False
        done_seen = False
        error_seen = False
        error_details: list[dict[str, str]] = []
        event_count = 0
        headers = {"Authorization": f"Bearer {self.token}"}

        response: Any | None = None
        exception: Exception | None = None
        try:
            response = self.http.post(
                f"{self.host}{STREAM_NAME}",
                json={"message": PROMPT, "stream": True},
                headers=headers,
                stream=True,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            if response.status_code != 200:
                exception = RuntimeError(f"status={response.status_code}")
            else:
                for event_name, data in sse_events(response):
                    event_count += 1
                    if event_name == "metadata":
                        metadata_seen = True
                    elif event_name == "token":
                        token_seen = True
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                    elif event_name == "error":
                        error_seen = True
                        error_details.append(_record_error_reason(data))
                    elif event_name == "done":
                        done_seen = True

                if not metadata_seen or not token_seen or not done_seen or error_seen:
                    reason_labels = sorted(
                        {f"{item['category']}:{item['reason']}" for item in error_details}
                    )
                    reason_suffix = f" reasons={','.join(reason_labels)}" if reason_labels else ""
                    exception = RuntimeError(
                        f"incomplete_sse metadata={metadata_seen} token={token_seen} "
                        f"done={done_seen} error={error_seen} events={event_count}{reason_suffix}"
                    )
        except Exception as exc:
            exception = exc
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response_length = event_count
            if response is not None:
                response_length = int(response.headers.get("content-length") or event_count)
                response.close()

            events.request.fire(
                request_type="SSE",
                name=STREAM_NAME,
                response_time=elapsed_ms,
                response_length=response_length,
                response=response,
                context={"stream_complete": exception is None},
                exception=exception,
            )
            if first_token_at is not None:
                events.request.fire(
                    request_type="SSE",
                    name=TTFT_NAME,
                    response_time=(first_token_at - started) * 1000,
                    response_length=event_count,
                    response=response,
                    context={"stream_complete": exception is None},
                    exception=None,
                )


__all__ = ["SmartClassSSEUser"]
