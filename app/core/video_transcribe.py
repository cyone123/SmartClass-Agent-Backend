from __future__ import annotations

import asyncio
import base64
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import (
    get_video_ffmpeg_bin,
    get_video_vision_api_key,
    get_video_vision_base_url,
    get_video_vision_model,
)
from app.core.progress import ProgressReporter
from app.core.speech import SpeechRuntime

VIDEO_AUDIO_EXTRACTION_STEP = "video_audio_extraction"
VIDEO_TRANSCRIPTION_STEP = "video_transcription"
VIDEO_KEYFRAME_EXTRACTION_STEP = "video_keyframe_extraction"
VIDEO_FRAME_CAPTIONING_STEP = "video_frame_captioning"
TRANSCRIPT_MAX_CHARS = 12000


@dataclass(frozen=True)
class VideoVisionConfig:
    model: str | None
    base_url: str | None
    api_key: str | None


def get_video_vision_config() -> VideoVisionConfig:
    return VideoVisionConfig(
        model=get_video_vision_model(),
        base_url=get_video_vision_base_url(),
        api_key=get_video_vision_api_key(),
    )


def _message_to_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def _truncate_transcript(text: str, *, max_chars: int = TRANSCRIPT_MAX_CHARS) -> str:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "\n[transcript truncated]"


class VideoTranscriptionRuntime:
    def __init__(
        self,
        *,
        speech_runtime: SpeechRuntime,
        ffmpeg_bin: str | None = None,
        vision_config: VideoVisionConfig | None = None,
    ) -> None:
        self.speech_runtime = speech_runtime
        self.ffmpeg_bin = (ffmpeg_bin or get_video_ffmpeg_bin()).strip()
        self.vision_config = vision_config or get_video_vision_config()
        self._vision_model: ChatOpenAI | None = None

    async def analyze(
        self,
        *,
        file_path: Path,
        filename: str,
        mime_type: str | None = None,
        progress_reporter: ProgressReporter | None = None,
    ) -> str:
        transcript_text: str | None = None
        frame_summary: str | None = None
        audio_error: str | None = None
        frame_error: str | None = None
        audio_extracted = False
        transcription_attempted = False
        keyframe_count = 0
        frame_caption_attempted = False

        with tempfile.TemporaryDirectory(prefix="video-attachment-") as temp_dir:
            temp_root = Path(temp_dir)
            audio_path = temp_root / "audio.wav"
            frame_dir = temp_root / "frames"
            frame_dir.mkdir(parents=True, exist_ok=True)

            print(f"[video] analyze start filename={filename} file_path={file_path}")

            # if progress_reporter is not None:
            #     progress_reporter.emit(
            #         VIDEO_AUDIO_EXTRACTION_STEP,
            #         "running",
            #         detail=f"正在抽取视频音频：{filename}",
            #     )
            progress_reporter.emit(
                        VIDEO_TRANSCRIPTION_STEP,
                        "running",
                        detail=f"正在转写视频音频：{filename}",
                    )
            try:
                await self.extract_audio(file_path=file_path, output_path=audio_path)
            except RuntimeError as exc:
                audio_error = str(exc)
                print(f"[video] extract_audio failed filename={filename} error={audio_error}")
                if progress_reporter is not None:
                    progress_reporter.emit(VIDEO_AUDIO_EXTRACTION_STEP, "failed", detail=audio_error)
            else:
                audio_extracted = True
                print(
                    f"[video] extract_audio success filename={filename} "
                    f"audio_path={audio_path} size={audio_path.stat().st_size if audio_path.exists() else 0}"
                )
                # if progress_reporter is not None:
                #     progress_reporter.emit(
                #         VIDEO_AUDIO_EXTRACTION_STEP,
                #         "success",
                #         detail=f"已完成音频抽取：{filename}",
                #     )
                #     progress_reporter.emit(
                #         VIDEO_TRANSCRIPTION_STEP,
                #         "running",
                #         detail=f"正在转写视频音频：{filename}",
                #     )
                try:
                    transcription_attempted = True
                    transcript = await self.speech_runtime.transcribe(
                        file_path=audio_path,
                        filename=f"{Path(filename).stem}.wav",
                        mime_type="audio/wav",
                    )
                    transcript_text = _truncate_transcript(transcript.text)
                except RuntimeError as exc:
                    audio_error = str(exc)
                    print(f"[video] transcription failed filename={filename} error={audio_error}")
                    if progress_reporter is not None:
                        progress_reporter.emit(VIDEO_TRANSCRIPTION_STEP, "failed", detail=audio_error)
                else:
                    print(
                        f"[video] transcription success filename={filename} "
                        f"text_len={len(transcript_text or '')}"
                    )
                    if progress_reporter is not None:
                        progress_reporter.emit(
                            VIDEO_TRANSCRIPTION_STEP,
                            "success",
                            detail=f"已完成音频转写：{filename}",
                        )

            if progress_reporter is not None:
                progress_reporter.emit(
                    VIDEO_KEYFRAME_EXTRACTION_STEP,
                    "running",
                    detail=f"正在抽取关键帧：{filename}",
                )
            try:
                frame_paths = await self.extract_keyframes(
                    file_path=file_path,
                    output_dir=frame_dir,
                )
            except RuntimeError as exc:
                frame_paths = []
                frame_error = str(exc)
                print(f"[video] extract_keyframes failed filename={filename} error={frame_error}")
                if progress_reporter is not None:
                    progress_reporter.emit(VIDEO_KEYFRAME_EXTRACTION_STEP, "failed", detail=frame_error)
            else:
                keyframe_count = len(frame_paths)
                print(f"[video] extract_keyframes success filename={filename} keyframe_count={keyframe_count}")
                detail = (
                    f"已抽取 {len(frame_paths)} 张关键帧：{filename}"
                    if frame_paths
                    else f"未抽取到关键帧：{filename}"
                )
                if progress_reporter is not None:
                    progress_reporter.emit(VIDEO_KEYFRAME_EXTRACTION_STEP, "success", detail=detail)

            if frame_paths:
                if progress_reporter is not None:
                    progress_reporter.emit(
                        VIDEO_FRAME_CAPTIONING_STEP,
                        "running",
                        detail=f"正在转述关键画面：{filename}",
                    )
                try:
                    frame_caption_attempted = True
                    frame_summary = await self.caption_keyframes(frame_paths=frame_paths, filename=filename)
                except RuntimeError as exc:
                    frame_error = str(exc)
                    print(f"[video] caption_keyframes failed filename={filename} error={frame_error}")
                    if progress_reporter is not None:
                        progress_reporter.emit(VIDEO_FRAME_CAPTIONING_STEP, "failed", detail=frame_error)
                else:
                    print(
                        f"[video] caption_keyframes success filename={filename} "
                        f"text_len={len(frame_summary or '')}"
                    )
                    if progress_reporter is not None:
                        progress_reporter.emit(
                            VIDEO_FRAME_CAPTIONING_STEP,
                            "success",
                            detail=f"已完成关键画面转述：{filename}",
                        )
            elif progress_reporter is not None:
                progress_reporter.emit(
                    VIDEO_FRAME_CAPTIONING_STEP,
                    "success",
                    detail=f"无关键帧可转述，已跳过：{filename}",
                )

        if not transcript_text and not frame_summary:
            error_parts = [f"Video analysis failed for {filename}: no transcript or frame summary was produced."]
            if audio_error:
                error_parts.append(f"audio_error={audio_error}")
            if frame_error:
                error_parts.append(f"frame_error={frame_error}")
            error_parts.append(
                "state="
                f"audio_extracted={audio_extracted},"
                f"transcription_attempted={transcription_attempted},"
                f"keyframe_count={keyframe_count},"
                f"frame_caption_attempted={frame_caption_attempted}"
            )
            raise RuntimeError(" ".join(error_parts))

        sections = [f"视频附件：{filename}"]
        if transcript_text:
            sections.append(f"音频转写：\n{transcript_text}")
        if frame_summary:
            sections.append(f"关键画面摘要：\n{frame_summary}")
        _ = mime_type
        return "\n\n".join(sections).strip()

    async def extract_audio(self, *, file_path: Path, output_path: Path) -> None:
        await self._run_ffmpeg(
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(file_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg audio extraction completed without producing a valid WAV file.")

    async def extract_keyframes(
        self,
        *,
        file_path: Path,
        output_dir: Path,
        interval_seconds: int = 15,
        max_frames: int = 6,
    ) -> list[Path]:
        output_pattern = output_dir / "frame_%03d.jpg"
        await self._run_ffmpeg(
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(file_path),
            "-vf",
            f"fps=1/{interval_seconds}",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "2",
            str(output_pattern),
        )
        return sorted(output_dir.glob("frame_*.jpg"))

    async def caption_keyframes(self, *, frame_paths: list[Path], filename: str) -> str:
        if not frame_paths:
            raise RuntimeError("No keyframes were provided for captioning.")

        model = self._get_vision_model()
        message_blocks: list[dict[str, object]] = [
            {
                "type": "text",
                "text": (
                    "你是一个教学视频画面分析助手。"
                    "下面会提供同一视频抽取出的多张关键帧。"
                    "请仅根据画面内容做简洁、客观的中文转述，"
                    "总结主要场景、板书/课件、人物动作和画面变化。"
                    "不要猜测音频内容，不要编造看不见的信息。"
                ),
            }
        ]
        for frame_path in frame_paths:
            payload = base64.b64encode(frame_path.read_bytes()).decode("ascii")
            message_blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{payload}"},
                }
            )

        try:
            response = await model.ainvoke([HumanMessage(content=message_blocks)])
        except Exception as exc:
            raise RuntimeError(f"Video frame captioning failed: {exc}") from exc

        summary = _message_to_text(
            response if isinstance(response, BaseMessage) else AIMessage(content=str(response))
        ).strip()
        if not summary:
            raise RuntimeError(f"Video frame captioning returned empty text for {filename}.")
        return summary

    async def _run_ffmpeg(self, *args: str) -> None:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                list(args),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"FFmpeg executable not found: {self.ffmpeg_bin}. Set VIDEO_FFMPEG_BIN or install ffmpeg."
            ) from exc
        except Exception as exc:
            error_message = str(exc).strip() or repr(exc)
            raise RuntimeError(f"FFmpeg invocation failed: {error_message}") from exc

        if completed.returncode == 0:
            return

        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        error_message = (stderr or stdout).decode("utf-8", errors="ignore").strip()
        if not error_message:
            error_message = f"ffmpeg exited with code {completed.returncode}"
        raise RuntimeError(f"FFmpeg command failed: {error_message}")

    def _get_vision_model(self) -> ChatOpenAI:
        if self._vision_model is not None:
            return self._vision_model

        if not self.vision_config.model:
            raise RuntimeError("Video vision model is not configured. Set VIDEO_VISION_MODEL or MODEL.")
        if not self.vision_config.base_url or not self.vision_config.api_key:
            raise RuntimeError(
                "Video vision model is not configured. Set VIDEO_VISION_BASE_URL/API_KEY or BASE_URL/API_KEY."
            )

        self._vision_model = ChatOpenAI(
            model=self.vision_config.model,
            base_url=self.vision_config.base_url,
            api_key=self.vision_config.api_key,
            streaming=False,
        )
        return self._vision_model


def create_video_transcription_runtime(*, speech_runtime: SpeechRuntime) -> VideoTranscriptionRuntime:
    return VideoTranscriptionRuntime(speech_runtime=speech_runtime)
