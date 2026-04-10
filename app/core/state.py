from __future__ import annotations

from typing import Annotated, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class TeachingMetadata(TypedDict):
    """教学要素"""
    subject: str | None                         # 学科，如"数学"
    grade: str | None                           # 年级，如"初二"
    topic: str | None                           # 课题名称，如"勾股定理"
    course_duration: str                        # 教学时长
    core_points: List[str] | None               # 核心知识点
    key_points: List[str] | None                # 重点
    difficult_points: List[str] | None          # 难点
    teaching_objectives: str                    # 教学目标
    is_complete: bool

class SubAgentResult(TypedDict):
    """子Agent产出结果"""
    status: Literal["pending", "success", "failed"]
    uri: str   # 输出内容的统一资源标识符

#主state
class TeachingAssistantState(TypedDict):
    # ── 消息历史（自动累加）──
    messages: Annotated[List[BaseMessage], add_messages]
    # ── 意图识别 & 完整性 ──
    intent: str                                 # 意图识别结果
    # ── 教学元数据 ──
    teaching_metadata: Optional[TeachingMetadata]
    # ── RAG ──
    rag_context: str                            # RAG整理后供LLM使用的上下文
    # ── 教学设计 ──
    teaching_design_plan: str                   # 完整教学设计方案（供子Agent使用）
    # ── 子 Agent 产出 ──
    ppt_result: SubAgentResult
    lesson_plan_result: SubAgentResult
    game_result: SubAgentResult
    # ── 反馈 & 迭代 ──
    user_feedback: Optional[str]
    feedback_type: Optional[Literal[
        "approve",          # 全部满意
        "modify_ppt",       # 只改PPT
        "modify_lesson_plan", # 只改教案
        "modify_game",      # 只改游戏
        "modify_all"        # 全部重改
    ]]
    iteration_count: int                        # 迭代次数（防无限循环）
    # ── 错误处理 ──
    error: Optional[str]
    retry_count: int