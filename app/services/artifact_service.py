from __future__ import annotations

import mimetypes
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_file_storage_root
from app.models.file import ArtifactFile
from app.services.file_service import ensure_plan_exists, ensure_thread_belongs_to_plan

ArtifactType = Literal["ppt", "docx", "html-game"]
ArtifactStatus = Literal["pending", "running", "ready", "failed"]

ARTIFACT_STATUS_PENDING: ArtifactStatus = "pending"
ARTIFACT_STATUS_RUNNING: ArtifactStatus = "running"
ARTIFACT_STATUS_READY: ArtifactStatus = "ready"
ARTIFACT_STATUS_FAILED: ArtifactStatus = "failed"
ARTIFACT_EXTENSIONS: dict[ArtifactType, str] = {
    "ppt": ".pptx",
    "docx": ".docx",
    "html-game": ".html",
}
ARTIFACT_MIME_TYPES: dict[str, str] = {
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
}
MAX_ERROR_MESSAGE_LENGTH = 2000
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(filename: str) -> str:
    safe_name = SAFE_NAME_PATTERN.sub("_", filename).strip("._")
    return safe_name or "artifact"


def _guess_mime_type(filename: str, fallback: str | None = None) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback or "application/octet-stream"


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _default_title(artifact_type: ArtifactType) -> str:
    mapping = {
        "ppt": "教学课件",
        "docx": "教案文档",
        "html-game": "互动小游戏",
    }
    return mapping[artifact_type]


def _build_original_name(title: str, artifact_type: ArtifactType) -> str:
    extension = ARTIFACT_EXTENSIONS[artifact_type]
    base_name = _sanitize_filename(title)
    if base_name.lower().endswith(extension):
        return base_name
    return f"{base_name}{extension}"


def _build_storage_path(
    *,
    thread_id: str,
    artifact_type: ArtifactType,
    run_id: str,
    original_name: str,
) -> tuple[str, Path]:
    safe_name = _sanitize_filename(original_name)
    stored_name = f"{run_id}_{safe_name}"
    storage_path = (
        get_file_storage_root()
        / "artifacts"
        / thread_id
        / artifact_type
        / stored_name
    )
    return stored_name, storage_path


def serialize_artifact(
    artifact: ArtifactFile,
    *,
    url: str | None = None,
    preview_url: str | None = None,
) -> dict[str, object]:
    return {
        "id": artifact.id,
        "type": artifact.artifact_type,
        "title": artifact.title,
        "status": artifact.status,
        "mime_type": artifact.mime_type,
        "plan_id": artifact.plan_id,
        "thread_id": artifact.thread_id,
        "extension": artifact.extension,
        "size_bytes": artifact.size_bytes,
        "url": url,
        "preview_url": preview_url,
        "error_message": artifact.error_message,
        "created_at": _serialize_timestamp(artifact.created_at),
        "updated_at": _serialize_timestamp(artifact.updated_at),
    }


async def create_running_artifact(
    db: AsyncSession,
    *,
    plan_id: int,
    thread_id: str,
    artifact_type: ArtifactType,
    run_id: str,
    title: str | None = None,
) -> ArtifactFile:
    await ensure_plan_exists(db, plan_id)
    await ensure_thread_belongs_to_plan(db, plan_id, thread_id)

    normalized_title = (title or _default_title(artifact_type)).strip() or _default_title(artifact_type)
    original_name = _build_original_name(normalized_title, artifact_type)
    stored_name, storage_path = _build_storage_path(
        thread_id=thread_id,
        artifact_type=artifact_type,
        run_id=run_id,
        original_name=original_name,
    )
    extension = Path(original_name).suffix.lower()
    mime_type = ARTIFACT_MIME_TYPES.get(extension, _guess_mime_type(original_name))

    artifact = ArtifactFile(
        plan_id=plan_id,
        thread_id=thread_id,
        artifact_type=artifact_type,
        title=normalized_title,
        original_name=original_name,
        stored_name=stored_name,
        extension=extension,
        mime_type=mime_type,
        size_bytes=0,
        storage_path=str(storage_path),
        status=ARTIFACT_STATUS_RUNNING,
        error_message=None,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def mark_artifact_ready(
    db: AsyncSession,
    artifact: ArtifactFile,
    *,
    output_path: str | Path,
    title: str | None = None,
) -> ArtifactFile:
    source_path = Path(output_path)
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"Artifact output file not found: {source_path}")

    destination_path = Path(artifact.storage_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)

    artifact.title = (title or artifact.title).strip() or artifact.title
    artifact.original_name = source_path.name
    artifact.extension = source_path.suffix.lower()
    artifact.mime_type = ARTIFACT_MIME_TYPES.get(
        artifact.extension,
        _guess_mime_type(source_path.name, artifact.mime_type),
    )
    artifact.size_bytes = destination_path.stat().st_size
    artifact.storage_path = str(destination_path)
    artifact.status = ARTIFACT_STATUS_READY
    artifact.error_message = None
    artifact.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def mark_artifact_failed(
    db: AsyncSession,
    artifact: ArtifactFile,
    *,
    error_message: str,
) -> ArtifactFile:
    artifact.status = ARTIFACT_STATUS_FAILED
    artifact.error_message = error_message[:MAX_ERROR_MESSAGE_LENGTH]
    artifact.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def list_artifacts_by_thread(
    db: AsyncSession,
    *,
    thread_id: str,
) -> list[ArtifactFile]:
    stmt = (
        select(ArtifactFile)
        .where(ArtifactFile.thread_id == thread_id)
        .order_by(ArtifactFile.created_at.desc(), ArtifactFile.id.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_artifact_by_id(
    db: AsyncSession,
    artifact_id: int,
) -> ArtifactFile | None:
    return await db.get(ArtifactFile, artifact_id)


async def require_artifact_by_id(
    db: AsyncSession,
    artifact_id: int,
) -> ArtifactFile:
    artifact = await get_artifact_by_id(db, artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found.",
        )
    return artifact
