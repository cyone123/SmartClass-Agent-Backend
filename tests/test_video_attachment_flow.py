from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import MethodType, SimpleNamespace

from fastapi import FastAPI, UploadFile
from httpx import ASGITransport, AsyncClient

from app.api.chat import router as chat_router
from app.core.agent import AgentRuntime
from app.core.progress import ProgressReporter, ProgressTracker
from app.core.speech import TranscriptionResult
from app.core.video_transcribe import VideoTranscriptionRuntime, VideoVisionConfig
from app.dependencies.db import get_db
from app.models.file import AttachmentFile
from app.services import file_service, session_service


class FakeAttachmentSession:
    def __init__(self) -> None:
        self.attachments: list[AttachmentFile] = []
        self._next_id = 1

    def add(self, record: AttachmentFile) -> None:
        if record not in self.attachments:
            self.attachments.append(record)

    async def flush(self) -> None:
        for attachment in self.attachments:
            if getattr(attachment, "id", None) is None:
                attachment.id = self._next_id
                self._next_id += 1

    async def commit(self) -> None:
        return None

    async def refresh(self, record: AttachmentFile) -> None:
        _ = record
        return None


def _noop_existing_attachment(*args, **kwargs):
    _ = args, kwargs

    async def _inner():
        return None

    return _inner()


def _make_attachment(
    *,
    attachment_id: int,
    original_name: str,
    extension: str,
    mime_type: str,
    storage_path: str,
) -> AttachmentFile:
    now = datetime.now(timezone.utc)
    return AttachmentFile(
        id=attachment_id,
        plan_id=1,
        thread_id="thread-1",
        original_name=original_name,
        stored_name=original_name,
        extension=extension,
        mime_type=mime_type,
        size_bytes=128,
        sha256=str(attachment_id) * 64,
        storage_path=storage_path,
        created_at=now,
        updated_at=now,
    )


def test_attachment_upload_accepts_mp4(tmp_path, monkeypatch) -> None:
    async def _noop(*args, **kwargs):
        _ = args, kwargs
        return None

    async def run() -> None:
        monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(file_service, "ensure_plan_exists", _noop)
        monkeypatch.setattr(file_service, "ensure_thread_belongs_to_plan", _noop)
        monkeypatch.setattr(file_service, "get_existing_attachment_by_hash", _noop_existing_attachment)

        db = FakeAttachmentSession()
        upload = UploadFile(
            file=BytesIO(b"video-bytes"),
            filename="lesson.mp4",
            size=len(b"video-bytes"),
        )

        attachment = await file_service.create_attachment_from_upload(
            db,
            plan_id=1,
            thread_id="thread-1",
            upload_file=upload,
        )

        assert attachment.extension == ".mp4"
        assert attachment.mime_type == "video/mp4"
        stored_path = tmp_path / "attachments" / "thread-1" / "lesson.mp4"
        assert stored_path.exists()
        assert stored_path.read_bytes() == b"video-bytes"

    asyncio.run(run())


def test_chat_stream_passes_video_attachments_to_agent_runtime(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"video")

    class FakeAgentRuntime:
        async def stream_agent_events(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            yield {"event": "token", "data": {"run_id": kwargs["run_id"], "text": "ok"}}

    async def fake_get_session_by_thread_id(db, thread_id):
        _ = db
        return SimpleNamespace(plan_id=1, thread_id=thread_id)

    async def fake_get_chat_attachments_by_ids(db, *, plan_id, thread_id, attachment_ids):
        _ = db, plan_id, thread_id, attachment_ids
        return [
            _make_attachment(
                attachment_id=8,
                original_name="lesson.mp4",
                extension=".mp4",
                mime_type="video/mp4",
                storage_path=str(video_path),
            )
        ]

    async def run() -> None:
        monkeypatch.setattr(session_service, "get_session_by_thread_id", fake_get_session_by_thread_id)
        monkeypatch.setattr(file_service, "get_chat_attachments_by_ids", fake_get_chat_attachments_by_ids)

        app = FastAPI()
        app.include_router(chat_router)

        async def override_db():
            yield None

        async def override_agent_runtime():
            return FakeAgentRuntime()

        from app.core.agent import get_agent_runtime

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_agent_runtime] = override_agent_runtime

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/chat/stream",
                json={
                    "message": "请分析这个视频附件",
                    "thread_id": "thread-1",
                    "attachment_ids": [8],
                },
            )

        assert response.status_code == 200
        assert "event: token" in response.text
        attachments = captured["kwargs"]["attachments"]
        assert isinstance(attachments, list)
        assert attachments[0].id == 8
        assert attachments[0].mime_type == "video/mp4"

    asyncio.run(run())


def test_build_attachment_text_combines_document_and_video_sections(tmp_path) -> None:
    document_path = tmp_path / "lesson.pdf"
    video_path = tmp_path / "lesson.mp4"
    document_path.write_bytes(b"pdf")
    video_path.write_bytes(b"video")

    class FakeVideoRuntime:
        async def analyze(self, *, file_path, filename, mime_type=None, progress_reporter=None):
            _ = file_path, filename, mime_type, progress_reporter
            return "视频附件：lesson.mp4\n\n关键画面摘要：\n老师在讲解函数图像。"

    async def fake_analyze_attachments(self, message, file_paths, **kwargs):
        _ = self, message, kwargs
        assert file_paths == [str(document_path)]
        return "文档中包含本节课的教学目标。"

    runtime = object.__new__(AgentRuntime)
    runtime.video_transcription_runtime = FakeVideoRuntime()
    runtime.analyze_attachments = MethodType(fake_analyze_attachments, runtime)

    attachments = [
        _make_attachment(
            attachment_id=1,
            original_name="lesson.pdf",
            extension=".pdf",
            mime_type="application/pdf",
            storage_path=str(document_path),
        ),
        _make_attachment(
            attachment_id=2,
            original_name="lesson.mp4",
            extension=".mp4",
            mime_type="video/mp4",
            storage_path=str(video_path),
        ),
    ]

    result = asyncio.run(runtime.build_attachment_text("请结合附件备课", attachments))
    assert "文档附件摘要" in result
    assert "文档中包含本节课的教学目标" in result
    assert "视频附件：lesson.mp4" in result
    assert "老师在讲解函数图像" in result
    assert "---" in result


def test_video_transcription_runtime_builds_expected_ffmpeg_commands(tmp_path) -> None:
    captured: list[tuple[str, ...]] = []
    source_path = tmp_path / "lesson.mp4"
    source_path.write_bytes(b"video")
    audio_path = tmp_path / "audio.wav"
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="hello")

    async def fake_run_ffmpeg(self, *args):
        captured.append(tuple(args))
        output = args[-1]
        if str(output).endswith(".wav"):
            audio_path.write_bytes(b"wav")
        else:
            (frame_dir / "frame_001.jpg").write_bytes(b"jpg")

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )
    runtime._run_ffmpeg = MethodType(fake_run_ffmpeg, runtime)

    async def run() -> None:
        await runtime.extract_audio(file_path=source_path, output_path=audio_path)
        await runtime.extract_keyframes(file_path=source_path, output_dir=frame_dir)

    asyncio.run(run())

    assert captured[0][0] == "ffmpeg"
    assert "-acodec" in captured[0]
    assert "pcm_s16le" in captured[0]
    assert "-ar" in captured[0]
    assert "16000" in captured[0]
    assert "-ac" in captured[0]
    assert "1" in captured[0]
    assert captured[1][0] == "ffmpeg"
    assert "-vf" in captured[1]
    assert "fps=1/15" in captured[1]
    assert "-frames:v" in captured[1]
    assert "6" in captured[1]


def test_video_transcription_runtime_formats_output_and_truncates_transcript(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "lesson.mp4"
    input_path.write_bytes(b"video")
    progress_events: list[dict[str, object]] = []

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="A" * 13000)

    async def fake_extract_audio(self, *, file_path, output_path):
        _ = self, file_path
        output_path.write_bytes(b"wav")

    async def fake_extract_keyframes(self, *, file_path, output_dir, interval_seconds=15, max_frames=6):
        _ = self, file_path, interval_seconds, max_frames
        frame_path = output_dir / "frame_001.jpg"
        frame_path.write_bytes(b"jpg")
        return [frame_path]

    async def fake_caption_keyframes(self, *, frame_paths, filename):
        _ = self, frame_paths, filename
        return "画面中老师正在讲解例题。"

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )
    monkeypatch.setattr(runtime, "extract_audio", MethodType(fake_extract_audio, runtime))
    monkeypatch.setattr(runtime, "extract_keyframes", MethodType(fake_extract_keyframes, runtime))
    monkeypatch.setattr(runtime, "caption_keyframes", MethodType(fake_caption_keyframes, runtime))

    reporter = ProgressReporter(
        ProgressTracker(run_id="run-1"),
        emit_event=lambda event: progress_events.append(event),
    )
    result = asyncio.run(
        runtime.analyze(
            file_path=input_path,
            filename="lesson.mp4",
            progress_reporter=reporter,
        )
    )

    assert "视频附件：lesson.mp4" in result
    assert "音频转写" in result
    assert "[transcript truncated]" in result
    assert "关键画面摘要" in result
    assert "老师正在讲解例题" in result

    step_keys = [
        step["step_key"]
        for event in progress_events
        for step in event["data"]["steps"]
        if step["status"] in {"running", "success"}
    ]
    assert "video_audio_extraction" in step_keys
    assert "video_transcription" in step_keys
    assert "video_keyframe_extraction" in step_keys
    assert "video_frame_captioning" in step_keys


def test_video_transcription_runtime_falls_back_to_frame_summary_when_audio_fails(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "lesson.mp4"
    input_path.write_bytes(b"video")

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="unused")

    async def fake_extract_audio(self, *, file_path, output_path):
        _ = self, file_path, output_path
        raise RuntimeError("audio stream missing")

    async def fake_extract_keyframes(self, *, file_path, output_dir, interval_seconds=15, max_frames=6):
        _ = self, file_path, interval_seconds, max_frames
        frame_path = output_dir / "frame_001.jpg"
        frame_path.write_bytes(b"jpg")
        return [frame_path]

    async def fake_caption_keyframes(self, *, frame_paths, filename):
        _ = self, frame_paths, filename
        return "学生正在观看课件。"

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )
    monkeypatch.setattr(runtime, "extract_audio", MethodType(fake_extract_audio, runtime))
    monkeypatch.setattr(runtime, "extract_keyframes", MethodType(fake_extract_keyframes, runtime))
    monkeypatch.setattr(runtime, "caption_keyframes", MethodType(fake_caption_keyframes, runtime))

    result = asyncio.run(runtime.analyze(file_path=input_path, filename="lesson.mp4"))
    assert "关键画面摘要" in result
    assert "学生正在观看课件" in result
    assert "音频转写" not in result


def test_video_transcription_runtime_falls_back_to_transcript_when_no_keyframes(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "lesson.mp4"
    input_path.write_bytes(b"video")

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="这是一段课堂讲解录音。")

    async def fake_extract_audio(self, *, file_path, output_path):
        _ = self, file_path
        output_path.write_bytes(b"wav")

    async def fake_extract_keyframes(self, *, file_path, output_dir, interval_seconds=15, max_frames=6):
        _ = self, file_path, output_dir, interval_seconds, max_frames
        return []

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )
    monkeypatch.setattr(runtime, "extract_audio", MethodType(fake_extract_audio, runtime))
    monkeypatch.setattr(runtime, "extract_keyframes", MethodType(fake_extract_keyframes, runtime))

    result = asyncio.run(runtime.analyze(file_path=input_path, filename="lesson.mp4"))
    assert "音频转写" in result
    assert "这是一段课堂讲解录音" in result
    assert "关键画面摘要" not in result


def test_video_transcription_runtime_surfaces_missing_ffmpeg(tmp_path) -> None:
    input_path = tmp_path / "lesson.mp4"
    input_path.write_bytes(b"video")

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="unused")

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg-does-not-exist-for-tests",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )

    async def run() -> None:
        await runtime.extract_audio(file_path=input_path, output_path=tmp_path / "audio.wav")

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        assert "FFmpeg executable not found" in str(exc)
    else:
        raise AssertionError("Expected missing ffmpeg error.")


def test_video_transcription_runtime_surfaces_invocation_error_when_runner_has_empty_message(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "lesson.mp4"
    input_path.write_bytes(b"video")

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="unused")

    async def fake_to_thread(func, *args, **kwargs):
        _ = func, args, kwargs
        raise NotImplementedError()

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )
    monkeypatch.setattr("app.core.video_transcribe.asyncio.to_thread", fake_to_thread)

    async def run() -> None:
        await runtime.extract_audio(file_path=input_path, output_path=tmp_path / "audio.wav")

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        assert "FFmpeg invocation failed: NotImplementedError()" in str(exc)
    else:
        raise AssertionError("Expected ffmpeg invocation failure.")


def test_video_transcription_runtime_reports_both_audio_and_frame_errors(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "lesson.mp4"
    input_path.write_bytes(b"video")

    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="unused")

    async def fake_extract_audio(self, *, file_path, output_path):
        _ = self, file_path, output_path
        raise RuntimeError("ffmpeg audio failed")

    async def fake_extract_keyframes(self, *, file_path, output_dir, interval_seconds=15, max_frames=6):
        _ = self, file_path, output_dir, interval_seconds, max_frames
        raise RuntimeError("ffmpeg frame failed")

    runtime = VideoTranscriptionRuntime(
        speech_runtime=FakeSpeechRuntime(),
        ffmpeg_bin="ffmpeg",
        vision_config=VideoVisionConfig(model="vision-model", base_url="https://example.com", api_key="key"),
    )
    monkeypatch.setattr(runtime, "extract_audio", MethodType(fake_extract_audio, runtime))
    monkeypatch.setattr(runtime, "extract_keyframes", MethodType(fake_extract_keyframes, runtime))

    try:
        asyncio.run(runtime.analyze(file_path=input_path, filename="lesson.mp4"))
    except RuntimeError as exc:
        message = str(exc)
        assert "audio_error=ffmpeg audio failed" in message
        assert "frame_error=ffmpeg frame failed" in message
    else:
        raise AssertionError("Expected combined analysis error.")
