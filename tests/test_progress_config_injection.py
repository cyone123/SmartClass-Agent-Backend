from __future__ import annotations

from langgraph._internal._runnable import RunnableCallable

from app.core.graph import (
    intent_router_node,
    metadata_structer_node,
    teaching_design_planner,
)


def _get_func_accepts(func):
    if func.__code__.co_flags & 0x80:
        runnable = RunnableCallable(None, func, trace=False)
    else:
        runnable = RunnableCallable(func, None, trace=False)
    return runnable.func_accepts


def test_progress_nodes_accept_config_injection() -> None:
    accepts_map = {
        "intent_router_node": _get_func_accepts(intent_router_node),
        "metadata_structer_node": _get_func_accepts(metadata_structer_node),
        "teaching_design_planner": _get_func_accepts(teaching_design_planner),
    }

    for node_name, func_accepts in accepts_map.items():
        assert "config" in func_accepts, f"{node_name} should accept injected config"
