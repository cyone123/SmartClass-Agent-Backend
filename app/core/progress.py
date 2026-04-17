from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping, TypedDict

from langchain_core.runnables import RunnableConfig

ProgressStepKey = Literal[
    "attachment_analysis",
    "video_audio_extraction",
    "video_transcription",
    "video_keyframe_extraction",
    "video_frame_captioning",
    "skill_activation",
    "code_preparation",
    "code_execution",
    "intent_recognition",
    "metadata_structuring",
    "metadata_review",
    "rag_retrieval",
    "teaching_design",
    "teaching_plan_review",
    "ppt_generation",
    "lesson_plan_generation",
    "game_generation",
]
ProgressStatus = Literal["pending", "running", "success", "failed"]

STEP_ORDER: tuple[ProgressStepKey, ...] = (
    "attachment_analysis",
    "video_audio_extraction",
    "video_transcription",
    "video_keyframe_extraction",
    "video_frame_captioning",
    "skill_activation",
    "code_preparation",
    "code_execution",
    "intent_recognition",
    "metadata_structuring",
    "metadata_review",
    "rag_retrieval",
    "teaching_design",
    "teaching_plan_review",
    "ppt_generation",
    "lesson_plan_generation",
    "game_generation",
)
STEP_LABELS: dict[ProgressStepKey, str] = {
    "attachment_analysis": "附件分析",
    "video_audio_extraction": "视频抽取音频",
    "video_transcription": "视频音频转写",
    "video_keyframe_extraction": "视频抽取关键帧",
    "video_frame_captioning": "视频画面转述",
    "skill_activation": "Skill 加载",
    "code_preparation": "代码准备",
    "code_execution": "代码执行",
    "intent_recognition": "意图识别",
    "metadata_structuring": "结构化要素提取",
    "rag_retrieval": "RAG 检索",
    "teaching_design": "生成教学设计",
    "ppt_generation": "生成课件",
    "lesson_plan_generation": "生成教案",
    "game_generation": "生成互动内容",
}

STEP_LABELS["metadata_review"] = "确认教学要素"
STEP_LABELS["teaching_plan_review"] = "确认教学计划"


class ProgressStep(TypedDict, total=False):
    step_key: ProgressStepKey
    label: str
    status: ProgressStatus
    detail: str
    started_at: str
    finished_at: str


class ProgressPayload(TypedDict):
    run_id: str
    phase: Literal["agent_workflow"]
    steps: list[ProgressStep]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProgressTracker:
    run_id: str
    steps: dict[ProgressStepKey, ProgressStep] = field(default_factory=dict)

    def update(
        self,
        step_key: ProgressStepKey,
        status: ProgressStatus,
        *,
        detail: str | None = None,
    ) -> ProgressPayload:
        step = self.steps.get(step_key)
        if step is None:
            step = {
                "step_key": step_key,
                "label": STEP_LABELS[step_key],
                "status": "pending",
            }
            self.steps[step_key] = step

        step["status"] = status
        if detail:
            step["detail"] = detail
        elif "detail" in step:
            step.pop("detail")

        if status == "running":
            step.setdefault("started_at", _iso_now())
            step.pop("finished_at", None)
        elif status in {"success", "failed"}:
            step.setdefault("started_at", _iso_now())
            step["finished_at"] = _iso_now()

        return {
            "run_id": self.run_id,
            "phase": "agent_workflow",
            "steps": self.snapshot(),
        }

    def snapshot(self) -> list[ProgressStep]:
        order_index = {step_key: index for index, step_key in enumerate(STEP_ORDER)}
        return [
            dict(step)
            for step in sorted(
                self.steps.values(),
                key=lambda item: order_index[item["step_key"]],
            )
        ]


class ProgressReporter:
    def __init__(
        self,
        tracker: ProgressTracker,
        emit_event: Callable[[dict[str, Any]], None],
    ) -> None:
        self._tracker = tracker
        self._emit_event = emit_event

    def emit(
        self,
        step_key: ProgressStepKey,
        status: ProgressStatus,
        *,
        detail: str | None = None,
    ) -> None:
        payload = self._tracker.update(step_key, status, detail=detail)
        self._emit_event({"event": "progress", "data": payload})


_REPORTER_REGISTRY: dict[str, ProgressReporter] = {}
_REPORTER_REGISTRY_LOCK = threading.Lock()


def register_progress_reporter(run_id: str, reporter: ProgressReporter) -> None:
    with _REPORTER_REGISTRY_LOCK:
        _REPORTER_REGISTRY[run_id] = reporter


def unregister_progress_reporter(run_id: str) -> None:
    with _REPORTER_REGISTRY_LOCK:
        _REPORTER_REGISTRY.pop(run_id, None)


def get_registered_progress_reporter(run_id: str | None) -> ProgressReporter | None:
    if not run_id:
        return None
    with _REPORTER_REGISTRY_LOCK:
        return _REPORTER_REGISTRY.get(run_id)


def get_progress_reporter(config: RunnableConfig | None) -> ProgressReporter | None:
    if not isinstance(config, Mapping):
        return None

    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        return None

    reporter = configurable.get("progress_reporter")
    if isinstance(reporter, ProgressReporter):
        return reporter

    run_id = configurable.get("run_id")
    if isinstance(run_id, str):
        return get_registered_progress_reporter(run_id)

    return None


def emit_progress(
    config: RunnableConfig | None,
    step_key: ProgressStepKey,
    status: ProgressStatus,
    *,
    detail: str | None = None,
) -> ProgressReporter | None:
    reporter = get_progress_reporter(config)
    if reporter is None:
        return None

    reporter.emit(step_key, status, detail=detail)
    return reporter
