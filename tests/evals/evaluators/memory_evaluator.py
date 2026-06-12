"""记忆检索与写入评估器"""
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


class MemoryEvaluator(BaseEvaluator):
    """记忆检索与写入评估器

    评估维度：
    - 是否正确加载用户 profile 记忆
    - 是否正确检索相关 experience 记忆
    - 是否避免加载不相关的记忆
    - 是否在适当时刻写入或更新记忆
    - 记忆内容是否避免保存完整隐私数据
    """

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
        """执行记忆评估

        步骤：
        1. 获取 Agent Runtime
        2. 执行 LangGraph
        3. 提取记忆相关输出
        4. 执行所有断言
        5. 计算加权分数
        6. 返回 EvalResult
        """
        start_time = time.time()
        run_id = f"eval_{uuid.uuid4().hex[:8]}"

        try:
            # 获取 runtime
            runtime = await self._get_runtime()
            graph = runtime.streaming_graph

            # 准备配置
            thread_id = case.input.get("thread_id", f"eval_thread_{uuid.uuid4().hex[:8]}")
            user_id = case.input.get("user_id", "eval_user_001")

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

            # 提取记忆相关输出
            profile_memory_context = result.get("profile_memory_context", "")
            experience_memory_context = result.get("experience_memory_context", "")
            loaded_experience_memories = result.get("loaded_experience_memories", [])
            memory_operations = result.get("memory_operations", [])

            actual_output = {
                "profile_memory_context": profile_memory_context,
                "experience_memory_context": experience_memory_context,
                "loaded_experience_memories": loaded_experience_memories,
                "memory_operations": memory_operations,
                "response": (
                    result.get("messages", [])[-1].content
                    if result.get("messages")
                    else ""
                ),
                # 用于隐私检查
                "privacy_exposure": self._calculate_privacy_exposure(
                    profile_memory_context, experience_memory_context
                ),
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

    def _calculate_privacy_exposure(
        self, profile_context: str, experience_context: str
    ) -> float:
        """计算隐私暴露程度 (0.0-1.0)

        评估记忆上下文中是否包含敏感个人信息。
        """
        combined = f"{profile_context} {experience_context}".lower()

        # 敏感关键词 - 表示可能泄露隐私
        privacy_keywords = [
            "电话",
            "邮箱",
            "地址",
            "身份证",
            "密码",
            "账户",
            "学号",
            "工号",
            "家庭地址",
            "手机号",
            "qq号",
            "微信号",
        ]

        found_keywords = [kw for kw in privacy_keywords if kw in combined]
        exposure = len(found_keywords) / len(privacy_keywords) if privacy_keywords else 0.0

        return min(1.0, exposure)
