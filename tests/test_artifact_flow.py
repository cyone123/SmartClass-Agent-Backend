from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from httpx import ASGITransport, AsyncClient

from app.api.file import router as file_router
from app.dependencies.db import get_db
from app.models.file import ArtifactFile, KnowledgeFile
from app.services import artifact_service, file_service


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalarResult(self._items)


class FakeAsyncSession:
    def __init__(self) -> None:
        self.artifacts: list[ArtifactFile] = []
        self._next_id = 1

    def add(self, record) -> None:
        if getattr(record, "id", None) is None:
            record.id = self._next_id
            self._next_id += 1
        now = datetime.now(timezone.utc)
        if getattr(record, "created_at", None) is None:
            record.created_at = now
        record.updated_at = now
        if isinstance(record, ArtifactFile) and record not in self.artifacts:
            self.artifacts.append(record)

    async def commit(self) -> None:
        return None

    async def refresh(self, record) -> None:
        return None

    async def get(self, model, artifact_id: int):
        if model is not ArtifactFile:
            return None
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None

    async def execute(self, stmt):
        _ = stmt
        ordered = sorted(
            self.artifacts,
            key=lambda artifact: (artifact.created_at, artifact.id),
            reverse=True,
        )
        return _FakeExecuteResult(ordered)


def test_artifact_service_creates_persists_and_lists_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def _noop(*args, **kwargs):
        _ = args, kwargs
        return None

    async def run() -> None:
        monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(artifact_service, "ensure_plan_exists", _noop)
        monkeypatch.setattr(artifact_service, "ensure_thread_belongs_to_plan", _noop)
        db = FakeAsyncSession()

        running = await artifact_service.create_running_artifact(
            db,
            plan_id=1,
            thread_id="thread-1",
            artifact_type="html-game",
            run_id="run-1",
            title="quiz",
        )
        assert running.status == artifact_service.ARTIFACT_STATUS_RUNNING
        assert "artifacts" in running.storage_path

        generated_html = tmp_path / "generated.html"
        generated_html.write_text("<html><body>quiz</body></html>", encoding="utf-8")

        ready = await artifact_service.mark_artifact_ready(
            db,
            running,
            output_path=generated_html,
            title="课堂互动",
        )
        assert ready.status == artifact_service.ARTIFACT_STATUS_READY
        stored_path = Path(ready.storage_path)
        assert stored_path.exists()
        assert stored_path.read_text(encoding="utf-8") == "<html><body>quiz</body></html>"

        failed = await artifact_service.create_running_artifact(
            db,
            plan_id=1,
            thread_id="thread-1",
            artifact_type="ppt",
            run_id="run-2",
            title="slides",
        )
        failed = await artifact_service.mark_artifact_failed(
            db,
            failed,
            error_message="missing pptxgenjs",
        )
        assert failed.status == artifact_service.ARTIFACT_STATUS_FAILED
        assert failed.error_message == "missing pptxgenjs"

        artifacts = await artifact_service.list_artifacts_by_thread(db, thread_id="thread-1")
        assert [artifact.id for artifact in artifacts] == [failed.id, ready.id]

    asyncio.run(run())


def test_file_api_supports_artifact_download_and_public_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://public.example.com")

        knowledge_path = tmp_path / "source.docx"
        knowledge_path.write_text("knowledge doc", encoding="utf-8")

        artifact_docx_path = tmp_path / "lesson.docx"
        artifact_docx_path.write_text("artifact docx", encoding="utf-8")

        artifact_html_path = tmp_path / "game.html"
        artifact_html_path.write_text("<html></html>", encoding="utf-8")

        now = datetime.now(timezone.utc)
        knowledge = KnowledgeFile(
            id=11,
            plan_id=1,
            original_name="source.docx",
            stored_name="source.docx",
            extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=knowledge_path.stat().st_size,
            sha256="k" * 64,
            storage_path=str(knowledge_path),
            status="ready",
            error_message=None,
            chunk_count=1,
            created_at=now,
            updated_at=now,
            indexed_at=now,
        )
        artifact_docx = ArtifactFile(
            id=21,
            plan_id=1,
            thread_id="thread-1",
            artifact_type="docx",
            title="教案",
            original_name="lesson.docx",
            stored_name="lesson.docx",
            extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=artifact_docx_path.stat().st_size,
            storage_path=str(artifact_docx_path),
            status="ready",
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        artifact_html = ArtifactFile(
            id=22,
            plan_id=1,
            thread_id="thread-1",
            artifact_type="html-game",
            title="互动页",
            original_name="game.html",
            stored_name="game.html",
            extension=".html",
            mime_type="text/html",
            size_bytes=artifact_html_path.stat().st_size,
            storage_path=str(artifact_html_path),
            status="ready",
            error_message=None,
            created_at=now,
            updated_at=now,
        )

        async def fake_get_file_by_id(db, file_id, *, include_deleted=False):
            _ = db, include_deleted
            return knowledge if file_id == knowledge.id else None

        async def fake_get_artifact_by_id(db, artifact_id):
            _ = db
            if artifact_id == artifact_docx.id:
                return artifact_docx
            if artifact_id == artifact_html.id:
                return artifact_html
            return None

        async def fake_list_artifacts_by_thread(db, *, thread_id):
            _ = db
            return [artifact_html, artifact_docx] if thread_id == "thread-1" else []

        monkeypatch.setattr(file_service, "get_file_by_id", fake_get_file_by_id)
        monkeypatch.setattr(artifact_service, "get_artifact_by_id", fake_get_artifact_by_id)
        monkeypatch.setattr(artifact_service, "list_artifacts_by_thread", fake_list_artifacts_by_thread)

        app = FastAPI()
        app.include_router(file_router)

        async def override_db():
            yield None

        app.dependency_overrides[get_db] = override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            artifact_list = await client.get("/file/artifact", params={"thread_id": "thread-1"})
            assert artifact_list.status_code == 200
            assert artifact_list.json()["data"][0]["thread_id"] == "thread-1"
            assert artifact_list.json()["data"][0]["preview_url"].startswith(
                "https://public.example.com/file/preview/artifact/"
            )

            artifact_config = await client.get(f"/file/config/artifact/{artifact_docx.id}")
            assert artifact_config.status_code == 200
            config_payload = artifact_config.json()
            assert config_payload["document"]["url"].startswith("https://public.example.com/file/download/artifact/")
            assert config_payload["editorConfig"]["callbackUrl"] == "https://public.example.com/file/callback"
            assert config_payload["editorConfig"]["mode"] == "view"

            knowledge_config = await client.get(f"/file/config/knowledge/{knowledge.id}")
            assert knowledge_config.status_code == 200

            html_config = await client.get(f"/file/config/artifact/{artifact_html.id}")
            assert html_config.status_code == 400

            html_content = await client.get(f"/file/content/artifact/{artifact_html.id}")
            assert html_content.status_code == 200
            assert html_content.headers["content-type"].startswith("text/html")
            assert "content-disposition" not in html_content.headers
            assert html_content.text == "<html></html>"

            html_preview = await client.get(f"/file/preview/artifact/{artifact_html.id}")
            assert html_preview.status_code == 200
            assert html_preview.headers["content-type"].startswith("text/html")
            assert "sandbox=\"allow-scripts allow-modals\"" in html_preview.text
            assert f"/file/content/artifact/{artifact_html.id}" in html_preview.text

            artifact_download = await client.get(f"/file/download/artifact/{artifact_docx.id}")
            assert artifact_download.status_code == 200
            assert artifact_download.text == "artifact docx"

            html_download = await client.get(f"/file/download/artifact/{artifact_html.id}")
            assert html_download.status_code == 200
            assert "attachment" in html_download.headers.get("content-disposition", "").lower()

            missing_html_preview = await client.get("/file/preview/artifact/999")
            assert missing_html_preview.status_code == 404

            invalid_html_content = await client.get(f"/file/content/artifact/{artifact_docx.id}")
            assert invalid_html_content.status_code == 400

    asyncio.run(run())


def test_artifact_payload_and_sse_event_are_json_serializable() -> None:
    now = datetime.now(timezone.utc)
    artifact = ArtifactFile(
        id=31,
        plan_id=2,
        thread_id="thread-2",
        artifact_type="docx",
        title="Lesson Plan",
        original_name="lesson.docx",
        stored_name="run-lesson.docx",
        extension=".docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=128,
        storage_path="D:/fake/lesson.docx",
        status="running",
        error_message=None,
        created_at=now,
        updated_at=now,
    )

    payload = artifact_service.serialize_artifact(artifact)

    assert payload["created_at"] == now.isoformat()
    assert payload["updated_at"] == now.isoformat()

    encoded = json.dumps(jsonable_encoder({"artifact": payload}), ensure_ascii=False)
    assert now.isoformat() in encoded
