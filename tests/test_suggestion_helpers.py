from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.agent import (
    SUGGESTION_COUNT,
    _build_suggestion_conversation,
    _split_suggestion_lines,
    _sanitize_suggestions,
)


def test_split_suggestion_lines_uses_newlines() -> None:
    suggestions = _split_suggestion_lines(
        "第一条建议\n\n第二条建议\r\n第三条建议\n第四条建议"
    )

    assert suggestions == [
        "第一条建议",
        "第二条建议",
        "第三条建议",
        "第四条建议",
    ]


def test_sanitize_suggestions_trims_dedupes_and_limits_count() -> None:
    suggestions = _sanitize_suggestions(
        [
            "1. 你能把这节课的导入环节再细化吗？",
            "  你能把这节课的导入环节再细化吗？  ",
            "- 能给我一个课堂互动活动示例吗？",
            "3、如何根据这个设计安排板书？",
            "额外的一条建议",
        ]
    )

    assert suggestions == [
        "你能把这节课的导入环节再细化吗？",
        "能给我一个课堂互动活动示例吗？",
        "如何根据这个设计安排板书？",
    ]
    assert len(suggestions) == SUGGESTION_COUNT


def test_build_suggestion_conversation_keeps_human_and_ai_messages_only() -> None:
    messages = [
        HumanMessage(content="帮我设计一节函数导入课"),
        AIMessage(content="可以，我们先明确年级和课时。"),
        ToolMessage(content="tool output", tool_call_id="tool-1"),
        HumanMessage(content="高一，45分钟。"),
    ]

    conversation = _build_suggestion_conversation(messages)

    assert conversation == [
        "用户: 帮我设计一节函数导入课",
        "AI: 可以，我们先明确年级和课时。",
        "用户: 高一，45分钟。",
    ]
