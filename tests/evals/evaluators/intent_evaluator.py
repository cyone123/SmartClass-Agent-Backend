"""意图识别评估器"""
from __future__ import annotations

import time
import uuid
from datetime import datetime

from app.core.agent import create_agent_runtime
from app.core.evaluation import EvalCase, EvalCaseStatus, EvalResult
from app.core.rag import create_rag_runtime
from app.core.skills import create_skill_registry
from app.core.speech import create_speech_runtime
from app.core.video_transcribe import create_video_transcription_runtime

from .base import BaseEvaluator


class IntentEvaluator(BaseEvaluator):
    """意图识别评估器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._runtime = None

    async def _get_runtime(self):
        """获取 Agent Runtime（延迟初始化）"""
        if self._runtime is None:
            # 初始化依赖
            rag_runtime = await create_rag_runtime()
            skill_registry = create_skill_registry()
            speech_runtime = create_speech_runtime()
            video_runtime = create_video_transcription_runtime(
                speech_runtime=speech_runtime
            )

            self._runtime = await create_agent_runtime(
                rag_runtime=rag_runtime,
                skill_registry=skill_registry,
                video_transcription_runtime=video_runtime,
            )
        return self._runtime

    async def evaluate(self, case: EvalCase) -> EvalResult:
        """执行评估"""
        start_time = time.time()
        run_id = f"eval_{uuid.uuid4().hex[:8]}"

        try:
            # 获取 runtime
            runtime = await self._get_runtime()
            graph = runtime.streaming_graph

            # 准备配置
            thread_id = case.input["thread_id"]
            user_id = case.input["user_id"]

            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "user_id": user_id,
                }
            }

            # 准备输入
            from langchain_core.messages import HumanMessage

            input_data = {
                "messages": [HumanMessage(content=case.input["message"])],
            }

            # 如果有 plan_id，添加到状态
            if case.input.get("plan_id"):
                input_data["plan_id"] = case.input["plan_id"]

            # 运行 graph
            result = await graph.ainvoke(input_data, config=config)

            # 提取关键输出
            actual_output = {
                "intent": result.get("intent"),
                "extracted_elements": result.get("teaching_metadata"),
                "response": (
                    result.get("messages", [])[-1].content
                    if result.get("messages")
                    else ""
                ),
                "rag_triggered": "rag_context" in result,
                "memory_operations": [],
            }

            # 执行所有断言
            assertion_results = []
            for assertion in case.assertions:
                assertion_result = await self._check_assertion(assertion, actual_output)
                assertion_results.append(assertion_result)

            # 计算加权分数
            total_weight = sum(a.weight for a in case.assertions)
            weighted_score = (
                sum(r["score"] * r["weight"] for r in assertion_results) / total_weight
                if total_weight > 0
                else 0.0
            )

            # 判断是否通过（所有权重 >= 0.5 的断言必须通过）
            all_critical_passed = all(
                r["passed"] for r in assertion_results if r["weight"] >= 0.5
            )
            status = (
                EvalCaseStatus.PASSED if all_critical_passed else EvalCaseStatus.FAILED
            )

            return EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                status=status,
                score=weighted_score,
                assertion_results=assertion_results,
                actual_output=actual_output,
                execution_time=time.time() - start_time,
                timestamp=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            return EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                status=EvalCaseStatus.ERROR,
                score=0.0,
                assertion_results=[],
                actual_output={},
                execution_time=time.time() - start_time,
                error_message=str(e),
                timestamp=datetime.utcnow().isoformat(),
            )
