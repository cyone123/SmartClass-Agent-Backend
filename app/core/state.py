from __future__ import annotations

from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class TeachingMetadata(TypedDict):
    subject: str | None
    grade: str | None
    topic: str | None
    course_duration: str
    core_points: list[str] | None
    key_points: list[str] | None
    difficult_points: list[str] | None
    teaching_objectives: str | None
    is_complete: bool


class SubAgentResult(TypedDict):
    status: Literal["pending", "running", "ready", "failed"]
    artifact_id: int | None
    artifact_type: Literal["ppt", "docx", "html-game"] | None
    title: str | None
    error: str | None


class TeachingAssistantState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    plan_id: NotRequired[int]
    intent: NotRequired[str]
    teaching_metadata: NotRequired[TeachingMetadata | None]
    rag_context: NotRequired[str]
    rag_results: NotRequired[list[dict[str, Any]]]
    teaching_design_plan: NotRequired[str]
    ppt_result: NotRequired[SubAgentResult]
    lesson_plan_result: NotRequired[SubAgentResult]
    game_result: NotRequired[SubAgentResult]
    user_feedback: NotRequired[str | None]
    feedback_type: NotRequired[
        Literal["approve", "modify_ppt", "modify_lesson_plan", "modify_game", "modify_all"]
        | None
    ]
    iteration_count: NotRequired[int]
    error: NotRequired[str | None]
    retry_count: NotRequired[int]
