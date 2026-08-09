from __future__ import annotations

from tests.benchmarks.sse_protocol import (
    classify_error_reason,
    nearest_percentile,
    parse_error_reason,
    sanitize_error_text,
    sse_events,
)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def iter_lines(self, *, decode_unicode: bool) -> list[bytes]:
        assert decode_unicode is True
        return self.payload.splitlines()


def test_sse_events_parse_event_and_multiline_data() -> None:
    response = FakeResponse(
        b"event: metadata\ndata: {\"run_id\":\"r1\"}\n\n"
        b"event: token\ndata: first\ndata: second\n\n"
        b"event: done\ndata: [DONE]\n\n"
    )

    assert list(sse_events(response)) == [
        ("metadata", '{"run_id":"r1"}'),
        ("token", "first\nsecond"),
        ("done", "[DONE]"),
    ]


def test_sse_events_flush_unterminated_final_event() -> None:
    response = FakeResponse(b"event: token\ndata: tail")

    assert list(sse_events(response)) == [("token", "tail")]


def test_nearest_percentile_uses_response_time_frequency() -> None:
    response_times = {10: 2, 20: 3, 100: 1}

    assert nearest_percentile(response_times, 0.50) == 20
    assert nearest_percentile(response_times, 0.95) == 100


def test_parse_error_reason_extracts_provider_message_and_category() -> None:
    detail = parse_error_reason(
        '{"error_category":"model_error","error_type":"RateLimitError",'
        '"message":"429 rate limit exceeded"}'
    )

    assert detail == {
        "category": "model_error",
        "reason": "rate_limit",
        "error_type": "RateLimitError",
        "message": "429 rate limit exceeded",
    }


def test_sanitize_error_text_redacts_credentials_and_urls() -> None:
    text = sanitize_error_text(
        "api_key=secret-value Bearer abc.def token https://api.example.test/v1?key=secret"
    )

    assert "secret-value" not in text
    assert "abc.def" not in text
    assert "?key=secret" not in text
    assert classify_error_reason("HTTP 503 service unavailable") == "upstream_5xx"
    assert classify_error_reason("response_format type is unavailable now") == "unsupported_response_format"


def test_parse_error_reason_extracts_provider_type_from_stringified_payload() -> None:
    detail = parse_error_reason(
        "Error code: 400 - {'error': {'message': 'response_format unavailable', "
        "'type': 'invalid_request_error', 'code': 'invalid_request_error'}}"
    )

    assert detail["error_type"] == "invalid_request_error"
    assert detail["reason"] == "unsupported_response_format"
