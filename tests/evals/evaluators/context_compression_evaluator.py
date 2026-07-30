"""Context compression evaluator."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.core.context_compression import (
    COMPRESSED_CONTEXT_MARKER,
    CompressionSettings,
    compress_state_messages,
    is_compressed_context_message,
    message_to_text,
)
from app.core.evaluation import EvalCase, EvalCaseStatus, EvalResult
from app.core.observability import RunContext

from .base import BaseEvaluator


class FakeCompressionModel:
    model_name = "eval-context-compressor"
    request_timeout = 5

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def get_num_tokens_from_messages(self, messages: list[Any]) -> int:
        return max(100, len(messages) * 100)

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        if self.fail:
            raise RuntimeError("eval compression failure")
        prompt = "\n\n".join(message_to_text(message) for message in messages)
        return AIMessage(content=(f"对话目标：完成 SmartClass 长对话上下文压缩。\n保留要点：{prompt[:800]}"))


class ContextCompressionEvaluator(BaseEvaluator):
    """Evaluate deterministic context compression behavior without external LLM calls."""

    async def evaluate(self, case: EvalCase) -> EvalResult:
        start_time = time.time()
        try:
            actual = await self._run_case(case)
            assertion_results = []
            total_weight = 0.0
            weighted_score = 0.0

            for assertion in case.assertions:
                result = await self._check_assertion(assertion, actual)
                assertion_results.append(result)
                weight = result.get("weight", assertion.weight)
                total_weight += weight
                weighted_score += result.get("score", 0.0) * weight

            score = weighted_score / total_weight if total_weight else 0.0
            status = EvalCaseStatus.PASSED if score >= 0.7 else EvalCaseStatus.FAILED
            return EvalResult(
                case_id=case.case_id,
                run_id=f"eval_ctx_{uuid4().hex[:8]}",
                status=status,
                score=score,
                assertion_results=assertion_results,
                actual_output=actual,
                execution_time=time.time() - start_time,
                run_mode="deterministic",
                model={"provider": "fake", "model": FakeCompressionModel.model_name},
            )
        except Exception as exc:
            return EvalResult(
                case_id=case.case_id,
                run_id=f"eval_ctx_{uuid4().hex[:8]}",
                status=EvalCaseStatus.ERROR,
                score=0.0,
                assertion_results=[],
                actual_output={},
                execution_time=time.time() - start_time,
                error_message=str(exc),
                run_mode="deterministic",
                model={"provider": "fake", "model": FakeCompressionModel.model_name},
            )

    async def _run_case(self, case: EvalCase) -> dict[str, Any]:
        context = case.context or {}
        state = {
            "messages": self._messages_from_case(case),
            "teaching_metadata": context.get("teaching_metadata"),
            "rag_context": context.get("rag_context"),
            "rag_results": context.get("rag_results") or [],
            "teaching_design_plan": context.get("teaching_design_plan"),
            "artifact_catalog": context.get("artifact_catalog") or [],
            "revision_results": context.get("revision_results") or [],
        }
        if context.get("simulate_pending_approval"):
            return {
                "compression_status": "skipped",
                "compression_reason": "pending_approval",
                "update_created": False,
                "stream_completed": True,
                "compressed_context": "",
                "has_compressed_marker": False,
                "teaching_metadata": state["teaching_metadata"] or {},
                "retained_message_count": 0,
                "artifact_catalog": state["artifact_catalog"],
            }

        result = await compress_state_messages(
            state,
            context=RunContext(run_id=f"eval_{case.case_id}", thread_id=case.input.get("thread_id")),
            sink=None,
            settings=CompressionSettings(
                enabled=True,
                trigger_tokens=int(context.get("trigger_tokens", 10)),
                keep_recent_turns=int(context.get("keep_recent_turns", 2)),
                max_output_tokens=512,
                max_preface_chars=3000,
            ),
            model=FakeCompressionModel(fail=bool(context.get("simulate_failure"))),
        )
        compressed_messages = [
            message for message in (result.update or {}).get("messages", []) if is_compressed_context_message(message)
        ]
        compressed_context = message_to_text(compressed_messages[0]) if compressed_messages else ""
        return {
            "compression_status": result.status,
            "compression_reason": result.reason,
            "update_created": result.update is not None,
            "stream_completed": True,
            "compressed_context": compressed_context,
            "has_compressed_marker": COMPRESSED_CONTEXT_MARKER in compressed_context,
            "teaching_metadata": state["teaching_metadata"] or {},
            "retained_message_count": result.retained_message_count,
            "artifact_catalog": state["artifact_catalog"],
        }

    def _messages_from_case(self, case: EvalCase) -> list[Any]:
        context = case.context or {}
        history = context.get("chat_history")
        if history:
            messages = []
            for index, item in enumerate(history):
                role = str(item.get("role") or "teacher")
                content = str(item.get("content") or "")
                if role in {"teacher", "human", "user"}:
                    messages.append(HumanMessage(id=f"h-{index}", content=content))
                else:
                    messages.append(AIMessage(id=f"a-{index}", content=content))
            return messages

        long_turn_count = int(context.get("long_turn_count", 8))
        topic = str((context.get("teaching_metadata") or {}).get("topic") or case.input.get("message") or "教学主题")
        messages = []
        for index in range(long_turn_count):
            messages.append(HumanMessage(id=f"h-{index}", content=f"第 {index} 轮：请继续设计{topic}课程。"))
            messages.append(AIMessage(id=f"a-{index}", content=f"第 {index} 轮回复：已保留{topic}课程设计要求。"))
        return messages
