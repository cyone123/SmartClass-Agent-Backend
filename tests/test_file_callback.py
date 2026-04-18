from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.api.file as file_api
from app.api.file import router as file_router
from app.dependencies.db import get_db
from app.models.file import KnowledgeFile
from app.services import file_service


class FakeAsyncSession:
    async def commit(self) -> None:
        return None

    async def refresh(self, record) -> None:
        return None


class FakeIngestionRuntime:
    def __init__(self) -> None:
        self.enqueued_ids: list[int] = []

    async def enqueue(self, file_id: int) -> None:
        self.enqueued_ids.append(file_id)


def test_onlyoffice_callback_saves_pdf_and_requeues_ingestion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        existing_path = tmp_path / "lesson.pdf"
        existing_path.write_bytes(b"old pdf bytes")

        now = datetime.now(timezone.utc)
        knowledge_file = KnowledgeFile(
            id=11,
            plan_id=3,
            original_name="lesson.pdf",
            stored_name="lesson.pdf",
            extension=".pdf",
            mime_type="application/pdf",
            size_bytes=existing_path.stat().st_size,
            sha256=hashlib.sha256(existing_path.read_bytes()).hexdigest(),
            storage_path=str(existing_path),
            status=file_service.FILE_STATUS_READY,
            error_message=None,
            chunk_count=4,
            created_at=now,
            updated_at=now,
            indexed_at=now,
        )

        async def fake_get_file_by_id(db, file_id, *, include_deleted=False):
            _ = db, include_deleted
            if file_id == knowledge_file.id:
                return knowledge_file
            return None

        def fake_download_onlyoffice_document(*, url: str, destination_path: Path):
            assert url == "https://documentserver.example.com/cache/edited.pdf"
            content = b"new pdf bytes from onlyoffice"
            destination_path.write_bytes(content)
            return file_api._DownloadedFileMetadata(
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )

        monkeypatch.setattr(file_service, "get_file_by_id", fake_get_file_by_id)
        monkeypatch.setattr(
            file_api,
            "_download_onlyoffice_document",
            fake_download_onlyoffice_document,
        )

        app = FastAPI()
        app.include_router(file_router)

        fake_db = FakeAsyncSession()
        fake_ingestion_runtime = FakeIngestionRuntime()

        async def override_db():
            yield fake_db

        async def override_ingestion_runtime():
            return fake_ingestion_runtime

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[file_api.get_file_ingestion_runtime] = override_ingestion_runtime

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/file/callback",
                json={
                    "key": "knowledge-11-1713400000",
                    "status": 2,
                    "url": "https://documentserver.example.com/cache/edited.pdf",
                },
            )

        assert response.status_code == 200
        assert response.json() == {"error": 0}
        assert existing_path.read_bytes() == b"new pdf bytes from onlyoffice"
        assert knowledge_file.size_bytes == len(b"new pdf bytes from onlyoffice")
        assert knowledge_file.sha256 == hashlib.sha256(
            b"new pdf bytes from onlyoffice"
        ).hexdigest()
        assert knowledge_file.status == file_service.FILE_STATUS_UPLOADED
        assert knowledge_file.chunk_count == 0
        assert knowledge_file.indexed_at is None
        assert fake_ingestion_runtime.enqueued_ids == [knowledge_file.id]
        assert knowledge_file.updated_at >= now

    asyncio.run(run())


def test_onlyoffice_callback_ignores_non_save_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        existing_path = tmp_path / "lesson.pdf"
        existing_path.write_bytes(b"unchanged")

        now = datetime.now(timezone.utc)
        knowledge_file = KnowledgeFile(
            id=12,
            plan_id=3,
            original_name="lesson.pdf",
            stored_name="lesson.pdf",
            extension=".pdf",
            mime_type="application/pdf",
            size_bytes=existing_path.stat().st_size,
            sha256=hashlib.sha256(existing_path.read_bytes()).hexdigest(),
            storage_path=str(existing_path),
            status=file_service.FILE_STATUS_READY,
            error_message=None,
            chunk_count=2,
            created_at=now,
            updated_at=now,
            indexed_at=now,
        )

        async def fake_get_file_by_id(db, file_id, *, include_deleted=False):
            _ = db, include_deleted
            if file_id == knowledge_file.id:
                return knowledge_file
            return None

        def fail_if_called(**kwargs):
            raise AssertionError(f"download helper should not be called: {kwargs}")

        monkeypatch.setattr(file_service, "get_file_by_id", fake_get_file_by_id)
        monkeypatch.setattr(file_api, "_download_onlyoffice_document", fail_if_called)

        app = FastAPI()
        app.include_router(file_router)

        fake_db = FakeAsyncSession()
        fake_ingestion_runtime = FakeIngestionRuntime()

        async def override_db():
            yield fake_db

        async def override_ingestion_runtime():
            return fake_ingestion_runtime

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[file_api.get_file_ingestion_runtime] = override_ingestion_runtime

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/file/callback",
                json={
                    "key": "knowledge-12-1713400000",
                    "status": 4,
                },
            )

        assert response.status_code == 200
        assert response.json() == {"error": 0}
        assert existing_path.read_bytes() == b"unchanged"
        assert fake_ingestion_runtime.enqueued_ids == []
        assert knowledge_file.status == file_service.FILE_STATUS_READY

    asyncio.run(run())
