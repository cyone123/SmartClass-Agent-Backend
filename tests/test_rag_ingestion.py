from __future__ import annotations

import asyncio
from io import BytesIO
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from langchain_core.documents import Document

from app.core.storage import LOCAL_STORAGE_BACKEND, reset_storage_service_for_tests
from app.core.rag import RagRuntime
from app.models.file import KnowledgeFile
from app.services import file_service


class FakeAsyncSession:
    async def commit(self) -> None:
        return None

    async def refresh(self, record) -> None:
        return None


class FakeUploadSession(FakeAsyncSession):
    def __init__(self) -> None:
        self.added = None

    def add(self, record) -> None:
        self.added = record

    async def flush(self) -> None:
        if self.added is not None and self.added.id is None:
            self.added.id = 42


class FakeRagRuntime:
    def __init__(self) -> None:
        self.deleted_file_ids: list[int] = []
        self.added_documents: list[Document] = []
        self.loaded_file_contents: list[bytes] = []

    def supports_file_extension(self, extension: str | None) -> bool:
        return extension in {".docx", ".txt", ".pdf", ".md", ".markdown", ".csv", ".json"}

    async def load_and_split_file(self, file_path: str) -> list[Document]:
        self.loaded_file_contents.append(Path(file_path).read_bytes())
        return [Document(page_content="docx chunk", metadata={"source": file_path})]

    async def delete_by_file_id(self, file_id: int) -> None:
        self.deleted_file_ids.append(file_id)

    async def add_documents(self, documents: list[Document]) -> None:
        self.added_documents.extend(documents)


def _create_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {paragraphs}
  </w:body>
</w:document>
""".format(
        paragraphs="".join(
            f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
            for text in paragraphs
        )
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def test_rag_runtime_load_and_split_txt_file(tmp_path: Path) -> None:
    async def run() -> None:
        text_path = tmp_path / "knowledge.txt"
        text_path.write_text("第一段知识点\n第二段知识点", encoding="utf-8")

        runtime = object.__new__(RagRuntime)
        documents = await RagRuntime.load_and_split_file(runtime, str(text_path))

        assert len(documents) == 1
        assert "第一段知识点" in documents[0].page_content
        assert documents[0].metadata["source"].endswith("knowledge.txt")
        assert "page" not in documents[0].metadata

    asyncio.run(run())


def test_rag_runtime_load_and_split_docx_file(tmp_path: Path) -> None:
    async def run() -> None:
        docx_path = tmp_path / "knowledge.docx"
        _create_minimal_docx(docx_path, ["教学目标", "重点难点"])

        runtime = object.__new__(RagRuntime)
        documents = await RagRuntime.load_and_split_file(runtime, str(docx_path))

        assert len(documents) == 1
        assert "教学目标" in documents[0].page_content
        assert "重点难点" in documents[0].page_content
        assert documents[0].metadata["source"].endswith("knowledge.docx")
        assert "page" not in documents[0].metadata

    asyncio.run(run())


def test_process_file_ingestion_supports_docx_files(tmp_path: Path, monkeypatch) -> None:
    async def run() -> None:
        docx_path = tmp_path / "lesson.docx"
        _create_minimal_docx(docx_path, ["课程导入", "课堂活动"])

        now = datetime.now(timezone.utc)
        knowledge_file = KnowledgeFile(
            id=18,
            plan_id=7,
            original_name="lesson.docx",
            stored_name="lesson.docx",
            extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=docx_path.stat().st_size,
            sha256="d" * 64,
            storage_path=str(docx_path),
            storage_backend=None,
            storage_key=None,
            status=file_service.FILE_STATUS_UPLOADED,
            error_message=None,
            chunk_count=0,
            created_at=now,
            updated_at=now,
            indexed_at=None,
        )

        async def fake_get_file_by_id(db, file_id, *, include_deleted=False, user_id=None):
            _ = db, include_deleted, user_id
            if file_id == knowledge_file.id:
                return knowledge_file
            return None

        monkeypatch.setattr(file_service, "get_file_by_id", fake_get_file_by_id)
        rag_runtime = FakeRagRuntime()
        db = FakeAsyncSession()

        await file_service.process_file_ingestion(
            db,
            file_id=knowledge_file.id,
            rag_runtime=rag_runtime,
            user_id=7,
        )

        assert rag_runtime.deleted_file_ids == [knowledge_file.id]
        assert len(rag_runtime.added_documents) == 1
        assert rag_runtime.added_documents[0].page_content == "docx chunk"
        assert rag_runtime.added_documents[0].metadata == {
            "source": str(docx_path),
            "plan_id": knowledge_file.plan_id,
            "file_id": knowledge_file.id,
            "source_name": knowledge_file.original_name,
            "chunk_index": 0,
            "page": None,
        }
        assert knowledge_file.status == file_service.FILE_STATUS_READY
        assert knowledge_file.chunk_count == 1
        assert knowledge_file.indexed_at is not None

    asyncio.run(run())


def test_create_knowledge_file_from_upload_uses_storage_service(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path / "objects"))
        reset_storage_service_for_tests()

        async def fake_ensure_plan_exists(db, plan_id, *, user_id=None):
            _ = db, plan_id, user_id
            return object()

        async def fake_get_existing_file_by_hash(db, *, plan_id, sha256, user_id):
            _ = db, plan_id, sha256, user_id
            return None

        monkeypatch.setattr(file_service, "ensure_plan_exists", fake_ensure_plan_exists)
        monkeypatch.setattr(file_service, "get_existing_file_by_hash", fake_get_existing_file_by_hash)

        upload = UploadFile(
            file=BytesIO(b"lesson knowledge"),
            filename="lesson.txt",
        )
        db = FakeUploadSession()

        record = await file_service.create_file_from_upload(
            db,
            plan_id=7,
            upload_file=upload,
            user_id=7,
        )

        assert record.storage_backend == LOCAL_STORAGE_BACKEND
        assert record.storage_key == "knowledge/user-7/plan-7/file-42/lesson.txt"
        assert record.storage_path
        assert Path(record.storage_path).read_bytes() == b"lesson knowledge"
        assert record.status == file_service.FILE_STATUS_UPLOADED

        reset_storage_service_for_tests()

    asyncio.run(run())


def test_process_file_ingestion_materializes_object_backed_knowledge_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path / "objects"))
        reset_storage_service_for_tests()

        upload = UploadFile(
            file=BytesIO(b"object backed lesson"),
            filename="lesson.txt",
        )

        async def fake_ensure_plan_exists(db, plan_id, *, user_id=None):
            _ = db, plan_id, user_id
            return object()

        async def fake_get_existing_file_by_hash(db, *, plan_id, sha256, user_id):
            _ = db, plan_id, sha256, user_id
            return None

        monkeypatch.setattr(file_service, "ensure_plan_exists", fake_ensure_plan_exists)
        monkeypatch.setattr(file_service, "get_existing_file_by_hash", fake_get_existing_file_by_hash)

        db = FakeUploadSession()
        knowledge_file = await file_service.create_file_from_upload(
            db,
            plan_id=7,
            upload_file=upload,
            user_id=7,
        )

        async def fake_get_file_by_id(db, file_id, *, include_deleted=False, user_id=None):
            _ = db, include_deleted, user_id
            if file_id == knowledge_file.id:
                return knowledge_file
            return None

        monkeypatch.setattr(file_service, "get_file_by_id", fake_get_file_by_id)
        rag_runtime = FakeRagRuntime()

        await file_service.process_file_ingestion(
            db,
            file_id=knowledge_file.id,
            rag_runtime=rag_runtime,
            user_id=7,
        )

        assert rag_runtime.deleted_file_ids == [knowledge_file.id]
        assert rag_runtime.loaded_file_contents == [b"object backed lesson"]
        assert len(rag_runtime.added_documents) == 1
        assert rag_runtime.added_documents[0].metadata["source"].endswith("lesson.txt")
        assert knowledge_file.status == file_service.FILE_STATUS_READY

        reset_storage_service_for_tests()

    asyncio.run(run())
