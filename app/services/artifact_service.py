from __future__ import annotations

import contextlib
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_file_storage_root
from app.core.storage import build_storage_key, get_storage_service
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
        "html-game": "互动内容",
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
    storage_path = get_file_storage_root() / "artifacts" / thread_id / artifact_type / stored_name
    return stored_name, storage_path


def _build_storage_key(
    *,
    thread_id: str,
    artifact_type: ArtifactType,
    run_id: str,
    stored_name: str,
) -> str:
    return build_storage_key(
        "artifacts",
        f"thread-{thread_id}",
        artifact_type,
        f"run-{run_id}",
        stored_name,
    )


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
        "storage_path": artifact.storage_path,
        "storage_backend": artifact.storage_backend,
        "storage_key": artifact.storage_key,
        "parent_artifact_id": artifact.parent_artifact_id,
        "root_artifact_id": artifact.root_artifact_id,
        "revision_number": artifact.revision_number,
        "is_current": artifact.is_current,
        "url": url,
        "preview_url": preview_url,
        "error_message": artifact.error_message,
        "created_at": _serialize_timestamp(artifact.created_at),
        "updated_at": _serialize_timestamp(artifact.updated_at),
    }


async def _list_artifacts(
    db: AsyncSession,
    *,
    thread_id: str,
    include_history: bool,
    user_id: int | None = None,
) -> list[ArtifactFile]:
    stmt = select(ArtifactFile).where(ArtifactFile.thread_id == thread_id)
    if user_id is not None:
        stmt = stmt.where(ArtifactFile.user_id == user_id)
    if not include_history:
        stmt = stmt.where(
            or_(
                ArtifactFile.is_current.is_(True),
                ArtifactFile.status == ARTIFACT_STATUS_RUNNING,
            )
        )
    stmt = stmt.order_by(ArtifactFile.created_at.desc(), ArtifactFile.id.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_artifacts_by_thread(
    db: AsyncSession,
    *,
    thread_id: str,
    include_history: bool = False,
    user_id: int | None = None,
) -> list[ArtifactFile]:
    return await _list_artifacts(db, thread_id=thread_id, include_history=include_history, user_id=user_id)


async def list_current_artifacts_by_thread(
    db: AsyncSession,
    *,
    thread_id: str,
    user_id: int | None = None,
) -> list[ArtifactFile]:
    artifacts = await _list_artifacts(db, thread_id=thread_id, include_history=False, user_id=user_id)
    return [artifact for artifact in artifacts if artifact.status == ARTIFACT_STATUS_READY or artifact.is_current]


async def get_latest_current_artifact_by_type(
    db: AsyncSession,
    *,
    thread_id: str,
    artifact_type: ArtifactType,
    user_id: int | None = None,
) -> ArtifactFile | None:
    stmt = (
        select(ArtifactFile)
        .where(
            ArtifactFile.thread_id == thread_id,
            *([ArtifactFile.user_id == user_id] if user_id is not None else []),
            ArtifactFile.artifact_type == artifact_type,
            ArtifactFile.is_current.is_(True),
        )
        .order_by(ArtifactFile.updated_at.desc(), ArtifactFile.id.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_latest_current_artifacts_by_thread(
    db: AsyncSession,
    *,
    thread_id: str,
    user_id: int | None = None,
) -> list[ArtifactFile]:
    artifacts = await list_current_artifacts_by_thread(db, thread_id=thread_id, user_id=user_id)
    latest_by_type: dict[str, ArtifactFile] = {}
    for artifact in artifacts:
        existing = latest_by_type.get(artifact.artifact_type)
        if existing is None or (artifact.updated_at, artifact.id) > (existing.updated_at, existing.id):
            latest_by_type[artifact.artifact_type] = artifact
    return sorted(
        latest_by_type.values(),
        key=lambda item: (item.updated_at, item.id),
        reverse=True,
    )


async def list_ready_current_artifacts_by_thread(
    db: AsyncSession,
    *,
    thread_id: str,
    user_id: int | None = None,
) -> list[ArtifactFile]:
    stmt = (
        select(ArtifactFile)
        .where(
            ArtifactFile.thread_id == thread_id,
            *([ArtifactFile.user_id == user_id] if user_id is not None else []),
            ArtifactFile.is_current.is_(True),
            ArtifactFile.status == ARTIFACT_STATUS_READY,
        )
        .order_by(ArtifactFile.updated_at.desc(), ArtifactFile.id.desc())
    )
    result = await db.execute(stmt)
    return [
        artifact
        for artifact in result.scalars().all()
        if artifact.thread_id == thread_id
        and artifact.is_current
        and artifact.status == ARTIFACT_STATUS_READY
    ]


async def list_latest_ready_current_artifacts_by_thread(
    db: AsyncSession,
    *,
    thread_id: str,
    user_id: int | None = None,
) -> list[ArtifactFile]:
    artifacts = await list_ready_current_artifacts_by_thread(db, thread_id=thread_id, user_id=user_id)
    latest_by_type: dict[str, ArtifactFile] = {}
    for artifact in artifacts:
        existing = latest_by_type.get(artifact.artifact_type)
        if existing is None or (artifact.updated_at, artifact.id) > (existing.updated_at, existing.id):
            latest_by_type[artifact.artifact_type] = artifact
    return sorted(
        latest_by_type.values(),
        key=lambda item: (item.updated_at, item.id),
        reverse=True,
    )


async def get_current_artifact_by_id(
    db: AsyncSession,
    artifact_id: int,
    *,
    user_id: int | None = None,
) -> ArtifactFile | None:
    stmt = select(ArtifactFile).where(
        ArtifactFile.id == artifact_id,
        ArtifactFile.is_current.is_(True),
    )
    if user_id is not None:
        stmt = stmt.where(ArtifactFile.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_running_artifact(
    db: AsyncSession,
    *,
    plan_id: int,
    thread_id: str,
    artifact_type: ArtifactType,
    run_id: str,
    user_id: int,
    title: str | None = None,
    parent_artifact_id: int | None = None,
    root_artifact_id: int | None = None,
    revision_number: int | None = None,
) -> ArtifactFile:
    await ensure_plan_exists(db, plan_id, user_id=user_id)
    await ensure_thread_belongs_to_plan(db, plan_id, thread_id, user_id=user_id)

    normalized_title = (title or _default_title(artifact_type)).strip() or _default_title(artifact_type)
    original_name = _build_original_name(normalized_title, artifact_type)
    stored_name, storage_path = _build_storage_path(
        thread_id=thread_id,
        artifact_type=artifact_type,
        run_id=run_id,
        original_name=original_name,
    )
    storage_key = _build_storage_key(
        thread_id=thread_id,
        artifact_type=artifact_type,
        run_id=run_id,
        stored_name=stored_name,
    )
    extension = Path(original_name).suffix.lower()
    mime_type = ARTIFACT_MIME_TYPES.get(extension, _guess_mime_type(original_name))
    initial_revision = revision_number or 1
    is_current = parent_artifact_id is None

    artifact = ArtifactFile(
        plan_id=plan_id,
        user_id=user_id,
        thread_id=thread_id,
        artifact_type=artifact_type,
        parent_artifact_id=parent_artifact_id,
        root_artifact_id=root_artifact_id,
        revision_number=initial_revision,
        is_current=is_current,
        title=normalized_title,
        original_name=original_name,
        stored_name=stored_name,
        extension=extension,
        mime_type=mime_type,
        size_bytes=0,
        storage_path=str(storage_path),
        storage_backend=get_storage_service().backend_type,
        storage_key=storage_key,
        status=ARTIFACT_STATUS_RUNNING,
        error_message=None,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)

    if artifact.root_artifact_id is None:
        artifact.root_artifact_id = artifact.id
        await db.commit()
        await db.refresh(artifact)

    return artifact


async def create_revision_artifact(
    db: AsyncSession,
    *,
    source_artifact: ArtifactFile,
    run_id: str,
    title: str | None = None,
) -> ArtifactFile:
    return await create_running_artifact(
        db,
        plan_id=source_artifact.plan_id,
        thread_id=source_artifact.thread_id,
        artifact_type=source_artifact.artifact_type,  # type: ignore[arg-type]
        run_id=run_id,
        title=title or source_artifact.title,
        user_id=source_artifact.user_id,
        parent_artifact_id=source_artifact.id,
        root_artifact_id=source_artifact.root_artifact_id or source_artifact.id,
        revision_number=(source_artifact.revision_number or 1) + 1,
    )


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

    storage_key = artifact.storage_key or _build_storage_key(
        thread_id=artifact.thread_id,
        artifact_type=artifact.artifact_type,  # type: ignore[arg-type]
        run_id=f"artifact-{artifact.id}",
        stored_name=artifact.stored_name or source_path.name,
    )
    stored_object = get_storage_service().put_file(
        key=storage_key,
        source_path=source_path,
        filename=source_path.name,
        mime_type=ARTIFACT_MIME_TYPES.get(
            source_path.suffix.lower(),
            _guess_mime_type(source_path.name, artifact.mime_type),
        ),
    )

    current_stmt = select(ArtifactFile).where(
        ArtifactFile.thread_id == artifact.thread_id,
        ArtifactFile.user_id == artifact.user_id,
        ArtifactFile.artifact_type == artifact.artifact_type,
        ArtifactFile.is_current.is_(True),
        ArtifactFile.id != artifact.id,
    )
    current_result = await db.execute(current_stmt)
    for current_artifact in current_result.scalars().all():
        current_artifact.is_current = False
        current_artifact.updated_at = datetime.now(timezone.utc)

    artifact.title = (title or artifact.title).strip() or artifact.title
    artifact.original_name = source_path.name
    artifact.stored_name = source_path.name
    artifact.extension = source_path.suffix.lower()
    artifact.mime_type = ARTIFACT_MIME_TYPES.get(
        artifact.extension,
        _guess_mime_type(source_path.name, artifact.mime_type),
    )
    artifact.size_bytes = stored_object.size_bytes
    artifact.storage_path = stored_object.storage_path or artifact.storage_path
    artifact.storage_backend = stored_object.backend
    artifact.storage_key = stored_object.key
    artifact.status = ARTIFACT_STATUS_READY
    artifact.is_current = True
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


async def get_artifact_by_id(
    db: AsyncSession,
    artifact_id: int,
    *,
    user_id: int | None = None,
) -> ArtifactFile | None:
    if user_id is None:
        return await db.get(ArtifactFile, artifact_id)
    stmt = select(ArtifactFile).where(ArtifactFile.id == artifact_id, ArtifactFile.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def require_artifact_by_id(
    db: AsyncSession,
    artifact_id: int,
    *,
    user_id: int | None = None,
) -> ArtifactFile:
    artifact = await get_artifact_by_id(db, artifact_id, user_id=user_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found.",
        )
    return artifact


@contextlib.contextmanager
def materialize_artifact_file(artifact: ArtifactFile) -> Iterator[Path]:
    with get_storage_service().materialize_temp_file(
        storage_backend=artifact.storage_backend,
        storage_key=artifact.storage_key,
        storage_path=artifact.storage_path,
        suffix=artifact.extension or Path(artifact.original_name).suffix,
    ) as file_path:
        yield file_path


@contextlib.contextmanager
def materialize_artifact_payload(source_artifact: dict[str, object]) -> Iterator[Path]:
    with get_storage_service().materialize_temp_file(
        storage_backend=source_artifact.get("storage_backend") if isinstance(source_artifact.get("storage_backend"), str) else None,
        storage_key=source_artifact.get("storage_key") if isinstance(source_artifact.get("storage_key"), str) else None,
        storage_path=source_artifact.get("storage_path") if isinstance(source_artifact.get("storage_path"), str) else None,
        suffix=Path(str(source_artifact.get("original_name") or "")).suffix,
    ) as file_path:
        yield file_path
