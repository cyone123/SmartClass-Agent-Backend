from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient

from app.api.chat import router as chat_router
from app.api.file import router as file_router
from app.core.speech import TranscriptionResult, get_speech_client_config, get_speech_runtime
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


def _noop_existing_attachment(*args: Any, **kwargs: Any):
    _ = args, kwargs

    async def _inner() -> None:
        return None

    return _inner()


def test_voice_attachment_upload_accepts_audio_and_regular_attachment_rejects_it(
    tmp_path,
    monkeypatch,
) -> None:
    async def _noop(*args, **kwargs):
        _ = args, kwargs
        return None

    async def run() -> None:
        monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(file_service, "ensure_plan_exists", _noop)
        monkeypatch.setattr(file_service, "ensure_thread_belongs_to_plan", _noop)
        monkeypatch.setattr(file_service, "get_existing_attachment_by_hash", _noop_existing_attachment)

        db = FakeAttachmentSession()
        voice_upload = UploadFile(
            file=BytesIO(b"voice-bytes"),
            filename="lesson.webm",
            size=len(b"voice-bytes"),
        )
        voice_attachment = await file_service.create_voice_attachment_from_upload(
            db,
            plan_id=1,
            thread_id="thread-1",
            upload_file=voice_upload,
        )
        assert voice_attachment.extension == ".webm"
        assert file_service.is_voice_attachment_extension(voice_attachment.extension)

        stored_path = tmp_path / "attachments" / "thread-1" / "lesson.webm"
        assert stored_path.exists()
        assert stored_path.read_bytes() == b"voice-bytes"

        invalid_upload = UploadFile(
            file=BytesIO(b"voice-bytes"),
            filename="lesson.webm",
            size=len(b"voice-bytes"),
        )
        try:
            await file_service.create_attachment_from_upload(
                db,
                plan_id=1,
                thread_id="thread-1",
                upload_file=invalid_upload,
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Unsupported file type" in exc.detail
        else:
            raise AssertionError("Document attachment upload unexpectedly accepted a voice file.")

    asyncio.run(run())


def test_voice_transcription_api_returns_attachment_and_transcript(monkeypatch) -> None:
    class FakeSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            return TranscriptionResult(text="老师您好", language="zh")

    async def fake_create_voice_attachment_from_upload(db, *, plan_id, thread_id, upload_file):
        _ = db, upload_file
        now = datetime.now(timezone.utc)
        return AttachmentFile(
            id=9,
            plan_id=plan_id,
            thread_id=thread_id,
            original_name="voice.webm",
            stored_name="voice.webm",
            extension=".webm",
            mime_type="audio/webm",
            size_bytes=12,
            sha256="a" * 64,
            storage_path="D:/voice.webm",
            created_at=now,
            updated_at=now,
        )

    async def run() -> None:
        monkeypatch.setattr(file_service, "create_voice_attachment_from_upload", fake_create_voice_attachment_from_upload)

        app = FastAPI()
        app.include_router(file_router)

        async def override_db():
            yield None

        async def override_speech_runtime():
            return FakeSpeechRuntime()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_speech_runtime] = override_speech_runtime

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/file/attachment/voice/transcribe",
                params={"plan_id": 1, "thread_id": "thread-1"},
                files={"file": ("voice.webm", b"voice", "audio/webm")},
            )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["attachment"]["id"] == 9
        assert payload["transcript"] == "老师您好"
        assert payload["language"] == "zh"

    asyncio.run(run())


def test_voice_transcription_api_surfaces_provider_error(monkeypatch) -> None:
    class FailingSpeechRuntime:
        async def transcribe(self, *, file_path, filename, mime_type=None):
            _ = file_path, filename, mime_type
            raise RuntimeError("Current speech provider does not support transcription.")

    async def fake_create_voice_attachment_from_upload(db, *, plan_id, thread_id, upload_file):
        _ = db, upload_file
        now = datetime.now(timezone.utc)
        return AttachmentFile(
            id=10,
            plan_id=plan_id,
            thread_id=thread_id,
            original_name="voice.webm",
            stored_name="voice.webm",
            extension=".webm",
            mime_type="audio/webm",
            size_bytes=12,
            sha256="b" * 64,
            storage_path="D:/voice.webm",
            created_at=now,
            updated_at=now,
        )

    async def run() -> None:
        monkeypatch.setattr(file_service, "create_voice_attachment_from_upload", fake_create_voice_attachment_from_upload)

        app = FastAPI()
        app.include_router(file_router)

        async def override_db():
            yield None

        async def override_speech_runtime():
            return FailingSpeechRuntime()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_speech_runtime] = override_speech_runtime

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/file/attachment/voice/transcribe",
                params={"plan_id": 1, "thread_id": "thread-1"},
                files={"file": ("voice.webm", b"voice", "audio/webm")},
            )
        assert response.status_code == 502
        assert "does not support transcription" in response.json()["detail"]

    asyncio.run(run())


def test_chat_stream_rejects_voice_attachments(monkeypatch) -> None:
    class FakeAgentRuntime:
        async def stream_agent_events(self, *args, **kwargs):
            _ = args, kwargs
            if False:
                yield None

    async def fake_get_session_by_thread_id(db, thread_id):
        _ = db
        return SimpleNamespace(plan_id=1, thread_id=thread_id)

    async def fake_get_attachments_by_ids(db, *, plan_id, thread_id, attachment_ids):
        _ = db, plan_id, thread_id, attachment_ids
        return [
            AttachmentFile(
                id=7,
                plan_id=1,
                thread_id="thread-1",
                original_name="voice.webm",
                stored_name="voice.webm",
                extension=".webm",
                mime_type="audio/webm",
                size_bytes=12,
                sha256="c" * 64,
                storage_path="D:/voice.webm",
            )
        ]

    async def run() -> None:
        monkeypatch.setattr(session_service, "get_session_by_thread_id", fake_get_session_by_thread_id)
        monkeypatch.setattr(file_service, "get_attachments_by_ids", fake_get_attachments_by_ids)

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
                    "message": "请分析这个附件",
                    "thread_id": "thread-1",
                    "attachment_ids": [7],
                },
            )
        assert response.status_code == 400
        assert "voice attachment" in response.json()["detail"]

    asyncio.run(run())


def test_speech_client_config_prefers_stt_env_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("MODEL", "chat-model")
    monkeypatch.setenv("BASE_URL", "https://generic.example.com")
    monkeypatch.setenv("API_KEY", "generic-key")
    monkeypatch.delenv("STT_MODEL", raising=False)
    monkeypatch.delenv("STT_BASE_URL", raising=False)
    monkeypatch.delenv("STT_API_KEY", raising=False)
    monkeypatch.delenv("STT_LANGUAGE", raising=False)

    fallback_config = get_speech_client_config()
    assert fallback_config.model == "chat-model"
    assert fallback_config.base_url == "https://generic.example.com"
    assert fallback_config.api_key == "generic-key"
    assert fallback_config.language is None

    monkeypatch.setenv("STT_MODEL", "whisper-1")
    monkeypatch.setenv("STT_BASE_URL", "https://stt.example.com")
    monkeypatch.setenv("STT_API_KEY", "stt-key")
    monkeypatch.setenv("STT_LANGUAGE", "zh")

    stt_config = get_speech_client_config()
    assert stt_config.model == "whisper-1"
    assert stt_config.base_url == "https://stt.example.com"
    assert stt_config.api_key == "stt-key"
    assert stt_config.language == "zh"
