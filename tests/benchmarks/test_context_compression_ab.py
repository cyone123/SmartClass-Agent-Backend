from __future__ import annotations

from app.core.context_compression import CompressionSettings, build_compressed_message
from tests.benchmarks.context_compression_ab import (
    _authoritative_state_digest,
    _message_digest,
    _percentile,
    _retention_metrics,
    aggregate_report,
    apply_compression_result,
    build_synthetic_state,
    build_turn_messages,
)


def _settings() -> CompressionSettings:
    return CompressionSettings(
        enabled=True,
        trigger_tokens=6000,
        keep_recent_turns=6,
        max_output_tokens=800,
        max_preface_chars=6000,
    )


def test_synthetic_thread_contains_stable_fact_anchors() -> None:
    state = build_synthetic_state()
    for turn in range(1, 31):
        state["messages"].extend(build_turn_messages(turn))

    compressed = build_compressed_message(
        state,
        (
            "已确认校园旗杆测高；不得记录学生姓名或联系方式；"
            "最终生成 PPT 课件和 DOCX 教案；仍需确认教室投影仪。"
        ),
        settings=_settings(),
    )
    state["messages"] = [compressed, *state["messages"][-12:]]
    retention = _retention_metrics(state, total_turns=30, keep_recent_turns=6)

    assert retention["historical_fact_recall_pct"] == 100
    assert retention["structured_fact_recall_pct"] == 100
    assert retention["recent_message_exact_match_pct"] == 100


def test_authoritative_digest_ignores_message_replacement() -> None:
    state = build_synthetic_state()
    before = _authoritative_state_digest(state)
    state["messages"].extend(build_turn_messages(1))

    assert _authoritative_state_digest(state) == before


def test_message_digest_detects_context_changes() -> None:
    state = build_synthetic_state()
    before = _message_digest(state)
    state["messages"].extend(build_turn_messages(1))

    assert _message_digest(state) != before


def test_apply_compression_result_is_noop_without_success() -> None:
    from app.core.context_compression import CompressionResult

    state = build_synthetic_state()
    state["messages"].extend(build_turn_messages(1))
    original = list(state["messages"])
    apply_compression_result(state, CompressionResult(status="failed", reason="test"))

    assert state["messages"] == original


def test_nearest_rank_percentile() -> None:
    assert _percentile([10, 20, 30, 40], 0.50) == 20
    assert _percentile([10, 20, 30, 40], 0.95) == 40


def test_aggregate_overall_latency_does_not_double_count_nested_snapshots() -> None:
    settings = _settings()
    controls = {
        turns: {
            "cumulative_prompt_tokens": turns * 100,
            "final_context_tokens": turns * 10,
            "final_message_count": turns * 2,
        }
        for turns in (30, 50, 100)
    }

    def snapshot(turns: int, latency: int) -> dict:
        return {
            "turns": turns,
            "cumulative_prompt_tokens": turns * 50,
            "final_context_tokens": turns * 5,
            "final_message_count": 13,
            "compression_attempts": 1,
            "compression_calls": 1,
            "failed_compressions": 0,
            "compression_attempt_latency_ms": [latency],
            "failure_fallback_preserved_pct": 100,
            "compression_estimated_overhead_tokens": 10,
            "authoritative_state_unchanged": True,
            "retention": {
                "historical_fact_recall_pct": 100,
                "structured_fact_recall_pct": 100,
                "recent_message_exact_match_pct": 100,
            },
        }

    treatments = [
        {30: snapshot(30, 10), 50: snapshot(50, 20), 100: snapshot(100, 30)},
        {30: snapshot(30, 40), 50: snapshot(50, 50), 100: snapshot(100, 60)},
    ]
    from datetime import UTC, datetime

    report = aggregate_report(
        controls=controls,
        treatments=treatments,
        settings=settings,
        model_name="fake",
        started_at=datetime.now(UTC),
        duration_seconds=1,
    )

    assert report["latency_overall"]["compression_attempts"] == 2
    assert report["latency_overall"]["p50_ms"] == 30
    assert report["latency_overall"]["p95_ms"] == 60
