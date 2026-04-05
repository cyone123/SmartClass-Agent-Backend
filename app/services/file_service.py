from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    get_allowed_upload_extensions,
    get_file_storage_root,
    get_file_upload_max_size_bytes,
)
from app.core.rag import RagRuntime
from app.models.file import AttachmentFile, KnowledgeFile
from app.models.plan import Plan
from app.models.session import Session

FILE_STATUS_UPLOADED = "uploaded"
FILE_STATUS_INDEXING = "indexing"
FILE_STATUS_READY = "ready"
FILE_STATUS_FAILED = "failed"
FILE_STATUS_DELETED = "deleted"
ACTIVE_FILE_STATUSES = (
    FILE_STATUS_UPLOADED,
    FILE_STATUS_INDEXING,
    FILE_STATUS_READY,
)


def _sanitize_filename(filename: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return safe_name or "file"


def _guess_mime_type(filename: str, fallback: str | None) -> str:
    guessed_type, _ = mimetypes.guess_type(filename)
    return guessed_type or fallback or "application/octet-stream"


def _build_storage_path(plan_id: int, file_id: int, original_name: str) -> tuple[str, Path]:
    safe_name = _sanitize_filename(original_name)
    stored_name = f"{file_id}_{safe_name}"
    storage_path = get_file_storage_root() / "plan_files" / str(plan_id) / stored_name
    return stored_name, storage_path


def _build_attachment_storage_path(
    plan_id: int,
    thread_id: str,
    attachment_id: int,
    original_name: str,
) -> tuple[str, Path]:
    safe_name = _sanitize_filename(original_name)
    stored_name = f"{attachment_id}_{safe_name}"
    storage_path = (
        get_file_storage_root() / "attachments" / str(plan_id) / thread_id / stored_name
    )
    return stored_name, storage_path


async def _read_and_validate_upload_file(upload_file: UploadFile) -> tuple[str, str, bytes, int, str, str]:
    original_name = upload_file.filename or "file.pdf"
    extension = Path(original_name).suffix.lower()
    allowed_extensions = get_allowed_upload_extensions()
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {extension or 'unknown'}.",
        )

    content = await upload_file.read()
    size_bytes = len(content)
    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file is not allowed.",
        )

    max_size = get_file_upload_max_size_bytes()
    if size_bytes > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds max size limit: {max_size} bytes.",
        )

    sha256 = hashlib.sha256(content).hexdigest()
    mime_type = _guess_mime_type(original_name, upload_file.content_type)
    return original_name, extension, content, size_bytes, sha256, mime_type


async def ensure_plan_exists(db: AsyncSession, plan_id: int) -> Plan:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found.",
        )
    return plan


async def ensure_thread_belongs_to_plan(
    db: AsyncSession,
    plan_id: int,
    thread_id: str,
) -> Session:
    stmt = select(Session).where(Session.thread_id == thread_id)
    result = await db.execute(stmt)
    session_record = result.scalar_one_or_none()
    if session_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} not found.",
        )
    if session_record.plan_id != plan_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Thread {thread_id} does not belong to plan {plan_id}.",
        )
    return session_record


async def get_file_by_id(
    db: AsyncSession,
    file_id: int,
    *,
    include_deleted: bool = False,
) -> KnowledgeFile | None:
    file_record = await db.get(KnowledgeFile, file_id)
    if file_record is None:
        return None
    if not include_deleted and file_record.status == FILE_STATUS_DELETED:
        return None
    return file_record


async def list_files_by_plan(db: AsyncSession, plan_id: int) -> list[KnowledgeFile]:
    stmt = (
        select(KnowledgeFile)
        .where(
            KnowledgeFile.plan_id == plan_id,
            KnowledgeFile.status != FILE_STATUS_DELETED,
        )
        .order_by(KnowledgeFile.id.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_existing_file_by_hash(
    db: AsyncSession,
    *,
    plan_id: int,
    sha256: str,
) -> KnowledgeFile | None:
    stmt = (
        select(KnowledgeFile)
        .where(
            KnowledgeFile.plan_id == plan_id,
            KnowledgeFile.sha256 == sha256,
            KnowledgeFile.status.in_(ACTIVE_FILE_STATUSES),
        )
        .order_by(KnowledgeFile.id.desc())
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_existing_attachment_by_hash(
    db: AsyncSession,
    *,
    plan_id: int,
    thread_id: str,
    sha256: str,
) -> AttachmentFile | None:
    stmt = (
        select(AttachmentFile)
        .where(
            AttachmentFile.plan_id == plan_id,
            AttachmentFile.thread_id == thread_id,
            AttachmentFile.sha256 == sha256,
        )
        .order_by(AttachmentFile.id.desc())
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_file_from_upload(
    db: AsyncSession,
    *,
    plan_id: int,
    upload_file: UploadFile,
) -> KnowledgeFile:
    await ensure_plan_exists(db, plan_id)
    original_name, extension, content, size_bytes, sha256, mime_type = (
        await _read_and_validate_upload_file(upload_file)
    )

    existing = await get_existing_file_by_hash(db, plan_id=plan_id, sha256=sha256)
    if existing is not None:
        return existing

    file_record = KnowledgeFile(
        plan_id=plan_id,
        original_name=original_name,
        stored_name="",
        extension=extension,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=sha256,
        storage_path="",
        status=FILE_STATUS_UPLOADED,
        error_message=None,
        chunk_count=0,
    )
    db.add(file_record)
    await db.flush()

    stored_name, storage_path = _build_storage_path(plan_id, file_record.id, original_name)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)

    file_record.stored_name = stored_name
    file_record.storage_path = str(storage_path)
    file_record.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(file_record)
    return file_record


async def create_attachment_from_upload(
    db: AsyncSession,
    *,
    plan_id: int,
    thread_id: str,
    upload_file: UploadFile,
) -> AttachmentFile:
    await ensure_plan_exists(db, plan_id)
    await ensure_thread_belongs_to_plan(db, plan_id, thread_id)
    original_name, extension, content, size_bytes, sha256, mime_type = (
        await _read_and_validate_upload_file(upload_file)
    )

    existing = await get_existing_attachment_by_hash(
        db,
        plan_id=plan_id,
        thread_id=thread_id,
        sha256=sha256,
    )
    if existing is not None:
        return existing

    attachment_record = AttachmentFile(
        plan_id=plan_id,
        thread_id=thread_id,
        original_name=original_name,
        stored_name="",
        extension=extension,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=sha256,
        storage_path="",
    )
    db.add(attachment_record)
    await db.flush()

    stored_name, storage_path = _build_attachment_storage_path(
        plan_id,
        thread_id,
        attachment_record.id,
        original_name,
    )
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)

    attachment_record.stored_name = stored_name
    attachment_record.storage_path = str(storage_path)
    attachment_record.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(attachment_record)
    return attachment_record


async def get_attachments_by_ids(
    db: AsyncSession,
    *,
    plan_id: int,
    thread_id: str,
    attachment_ids: list[int],
) -> list[AttachmentFile]:
    if not attachment_ids:
        return []

    unique_ids = list(dict.fromkeys(attachment_ids))
    stmt = select(AttachmentFile).where(
        AttachmentFile.plan_id == plan_id,
        AttachmentFile.thread_id == thread_id,
        AttachmentFile.id.in_(unique_ids),
    )
    result = await db.execute(stmt)
    attachments = list(result.scalars().all())
    attachment_by_id = {attachment.id: attachment for attachment in attachments}

    missing_ids = [attachment_id for attachment_id in unique_ids if attachment_id not in attachment_by_id]
    if missing_ids:
        missing_id = missing_ids[0]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Attachment {missing_id} not found for plan {plan_id} "
                f"and thread {thread_id}."
            ),
        )

    return [attachment_by_id[attachment_id] for attachment_id in attachment_ids]


async def get_attachment_storage_paths_by_ids(
    db: AsyncSession,
    *,
    plan_id: int,
    thread_id: str,
    attachment_ids: list[int],
) -> list[str]:
    attachments = await get_attachments_by_ids(
        db,
        plan_id=plan_id,
        thread_id=thread_id,
        attachment_ids=attachment_ids,
    )
    storage_paths: list[str] = []
    for attachment in attachments:
        if not attachment.storage_path or not Path(attachment.storage_path).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stored attachment content not found for attachment {attachment.id}.",
            )
        storage_paths.append(attachment.storage_path)
    return storage_paths


async def mark_file_indexing(db: AsyncSession, file_record: KnowledgeFile) -> KnowledgeFile:
    file_record.status = FILE_STATUS_INDEXING
    file_record.error_message = None
    file_record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(file_record)
    return file_record


async def mark_file_ready(
    db: AsyncSession,
    file_record: KnowledgeFile,
    *,
    chunk_count: int,
) -> KnowledgeFile:
    file_record.status = FILE_STATUS_READY
    file_record.chunk_count = chunk_count
    file_record.error_message = None
    file_record.indexed_at = datetime.now(timezone.utc)
    file_record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(file_record)
    return file_record


async def mark_file_failed(
    db: AsyncSession,
    file_record: KnowledgeFile,
    *,
    error_message: str,
) -> KnowledgeFile:
    file_record.status = FILE_STATUS_FAILED
    file_record.error_message = error_message[:2000]
    file_record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(file_record)
    return file_record


async def retry_file(db: AsyncSession, file_id: int) -> KnowledgeFile:
    file_record = await get_file_by_id(db, file_id, include_deleted=True)
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found.",
        )
    if file_record.status == FILE_STATUS_DELETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deleted file cannot be retried.",
        )
    file_record.status = FILE_STATUS_UPLOADED
    file_record.error_message = None
    file_record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(file_record)
    return file_record


async def mark_file_deleted(db: AsyncSession, file_record: KnowledgeFile) -> KnowledgeFile:
    file_record.status = FILE_STATUS_DELETED
    file_record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(file_record)
    return file_record


async def delete_file(
    db: AsyncSession,
    *,
    file_id: int,
    rag_runtime: RagRuntime,
) -> None:
    file_record = await get_file_by_id(db, file_id, include_deleted=True)
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found.",
        )

    await rag_runtime.delete_by_file_id(file_id)
    await mark_file_deleted(db, file_record)

    if file_record.storage_path:
        try:
            os.remove(file_record.storage_path)
        except FileNotFoundError:
            pass


async def get_recoverable_file_ids(db: AsyncSession) -> list[int]:
    stmt = (
        select(KnowledgeFile)
        .where(KnowledgeFile.status.in_((FILE_STATUS_UPLOADED, FILE_STATUS_INDEXING)))
        .order_by(KnowledgeFile.id.asc())
    )
    result = await db.execute(stmt)
    file_records = list(result.scalars().all())
    recoverable_ids: list[int] = []
    for file_record in file_records:
        if file_record.status == FILE_STATUS_INDEXING:
            file_record.status = FILE_STATUS_UPLOADED
            file_record.updated_at = datetime.now(timezone.utc)
        recoverable_ids.append(file_record.id)
    if file_records:
        await db.commit()
    return recoverable_ids


async def process_file_ingestion(
    db: AsyncSession,
    *,
    file_id: int,
    rag_runtime: RagRuntime,
) -> None:
    file_record = await get_file_by_id(db, file_id, include_deleted=True)
    if file_record is None or file_record.status == FILE_STATUS_DELETED:
        return

    await mark_file_indexing(db, file_record)

    try:
        if file_record.extension != ".pdf":
            raise ValueError(f"Unsupported extension for ingestion: {file_record.extension}")
        if not file_record.storage_path or not Path(file_record.storage_path).exists():
            raise FileNotFoundError(f"Missing storage file: {file_record.storage_path}")

        documents = await rag_runtime.load_and_split_file(file_record.storage_path)
        enriched_documents = []
        for index, document in enumerate(documents):
            page = document.metadata.get("page")
            normalized_page = int(page) if isinstance(page, int) else None
            document.metadata = {
                **document.metadata,
                "plan_id": file_record.plan_id,
                "file_id": file_record.id,
                "source_name": file_record.original_name,
                "chunk_index": index,
                "page": normalized_page,
            }
            enriched_documents.append(document)

        await rag_runtime.delete_by_file_id(file_record.id)
        await rag_runtime.add_documents(enriched_documents)
        await mark_file_ready(db, file_record, chunk_count=len(enriched_documents))
    except Exception as exc:
        await mark_file_failed(db, file_record, error_message=str(exc))
        raise
