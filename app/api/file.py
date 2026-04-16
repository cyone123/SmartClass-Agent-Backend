from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_public_api_base_url
from app.core.file_ingestion import FileIngestionRuntime, get_file_ingestion_runtime
from app.core.rag import RagRuntime, get_rag_runtime
from app.core.speech import SpeechRuntime, get_speech_runtime
from app.dependencies.db import get_db
from app.models.file import ArtifactFile as ArtifactFileModel
from app.models.file import KnowledgeFile as KnowledgeFileModel
from app.schemas.file import (
    ArtifactFileListResponse,
    AttachmentFileResponse,
    KnowledgeFileListResponse,
    KnowledgeFileResponse,
    VoiceTranscriptionResponse,
)
from app.schemas.response import success_response
from app.services import artifact_service, file_service

router = APIRouter()

FileKind = Literal["knowledge", "artifact"]
OfficePreviewExtensions = {"doc", "docx", "ppt", "pptx", "pdf"}
HTML_PREVIEW_EXTENSIONS = {"html", "htm"}


def _build_public_url(request: Request, route_name: str, **path_params: object) -> str:
    internal_url = str(request.url_for(route_name, **path_params))
    public_base_url = get_public_api_base_url()
    if not public_base_url:
        return internal_url

    parts = urlsplit(internal_url)
    return urlunsplit((urlsplit(public_base_url).scheme, urlsplit(public_base_url).netloc, parts.path, parts.query, ""))


def _serialize_artifact(record: ArtifactFileModel, request: Request) -> dict[str, object]:
    download_url = _build_public_url(
        request,
        "download_file_resource",
        file_kind="artifact",
        file_id=record.id,
    )
    preview_url = None
    if (
        record.status == artifact_service.ARTIFACT_STATUS_READY
        and record.extension.lstrip(".").lower() in HTML_PREVIEW_EXTENSIONS
        and record.artifact_type == "html-game"
    ):
        preview_url = _build_public_url(
            request,
            "preview_artifact_html",
            file_id=record.id,
        )
    return artifact_service.serialize_artifact(
        record,
        url=download_url if record.status == artifact_service.ARTIFACT_STATUS_READY else None,
        preview_url=preview_url,
    )


async def _get_file_record(
    db: AsyncSession,
    *,
    file_kind: FileKind,
    file_id: int,
) -> KnowledgeFileModel | ArtifactFileModel | None:
    if file_kind == "knowledge":
        return await file_service.get_file_by_id(db, file_id)
    return await artifact_service.get_artifact_by_id(db, file_id)


async def _require_ready_html_artifact(
    db: AsyncSession,
    file_id: int,
) -> ArtifactFileModel:
    artifact = await artifact_service.get_artifact_by_id(db, file_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact file {file_id} not found.",
        )
    if artifact.status != artifact_service.ARTIFACT_STATUS_READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTML preview is only available for ready artifacts.",
        )

    extension = artifact.extension.lstrip(".").lower()
    if artifact.artifact_type != "html-game" or extension not in HTML_PREVIEW_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTML preview is only supported for html-game artifacts.",
        )

    storage_path = Path(artifact.storage_path)
    if not storage_path.exists() or not storage_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file content not found.",
        )

    return artifact


@router.get("/file/knowledgeFile", response_model=KnowledgeFileListResponse)
async def list_knowledge_files(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeFileListResponse:
    files = await file_service.list_files_by_plan(db, plan_id)
    return success_response(data=files, response_model=KnowledgeFileListResponse)


@router.get("/file/artifact", response_model=ArtifactFileListResponse)
async def list_artifacts(
    thread_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ArtifactFileListResponse:
    artifacts = await artifact_service.list_artifacts_by_thread(db, thread_id=thread_id)
    payload = [_serialize_artifact(record, request) for record in artifacts]
    return success_response(data=payload, response_model=ArtifactFileListResponse)


@router.post("/file/knowledgeFile/upload", response_model=KnowledgeFileResponse)
async def upload_knowledge_file(
    plan_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ingestion_runtime: FileIngestionRuntime = Depends(get_file_ingestion_runtime),
) -> KnowledgeFileResponse:
    file_record = await file_service.create_file_from_upload(
        db,
        plan_id=plan_id,
        upload_file=file,
    )
    if file_record.status == file_service.FILE_STATUS_UPLOADED:
        await ingestion_runtime.enqueue(file_record.id)
    return success_response(data=file_record, response_model=KnowledgeFileResponse)


@router.post("/file/attachment/upload", response_model=AttachmentFileResponse)
async def upload_attachment_file(
    plan_id: int,
    thread_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> AttachmentFileResponse:
    attachment_record = await file_service.create_attachment_from_upload(
        db,
        plan_id=plan_id,
        thread_id=thread_id,
        upload_file=file,
    )
    return success_response(
        data=attachment_record,
        response_model=AttachmentFileResponse,
    )


@router.post("/file/attachment/voice/transcribe", response_model=VoiceTranscriptionResponse)
async def transcribe_voice_attachment(
    plan_id: int,
    thread_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    speech_runtime: SpeechRuntime = Depends(get_speech_runtime),
) -> VoiceTranscriptionResponse:
    attachment_record = await file_service.create_voice_attachment_from_upload(
        db,
        plan_id=plan_id,
        thread_id=thread_id,
        upload_file=file,
    )
    try:
        transcription = await speech_runtime.transcribe(
            file_path=Path(attachment_record.storage_path),
            filename=attachment_record.original_name,
            mime_type=attachment_record.mime_type,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    payload = {
        "attachment": attachment_record,
        "transcript": transcription.text,
        "language": transcription.language,
    }
    return success_response(
        data=payload,
        response_model=VoiceTranscriptionResponse,
    )


@router.post("/file/{file_id}/retry", response_model=KnowledgeFileResponse)
async def retry_file_ingestion(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    ingestion_runtime: FileIngestionRuntime = Depends(get_file_ingestion_runtime),
) -> KnowledgeFileResponse:
    file_record = await file_service.retry_file(db, file_id)
    await ingestion_runtime.enqueue(file_record.id)
    return success_response(data=file_record, response_model=KnowledgeFileResponse)


@router.delete("/file/{file_id}")
async def delete_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    rag_runtime: RagRuntime = Depends(get_rag_runtime),
):
    await file_service.delete_file(db, file_id=file_id, rag_runtime=rag_runtime)
    return success_response()


@router.get("/file/download/{file_kind}/{file_id}", name="download_file_resource")
async def download_file_resource(
    file_kind: FileKind,
    file_id: int,
    db: AsyncSession = Depends(get_db),
):
    file_record = await _get_file_record(db, file_kind=file_kind, file_id=file_id)
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{file_kind.title()} file {file_id} not found.",
        )

    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file content not found.",
        )
    filename = getattr(file_record, "original_name", storage_path.name)
    return FileResponse(
        path=storage_path,
        media_type=file_record.mime_type,
        filename=filename,
    )


@router.get("/file/content/artifact/{file_id}", name="artifact_html_content")
async def get_artifact_html_content(
    file_id: int,
    db: AsyncSession = Depends(get_db),
):
    artifact = await _require_ready_html_artifact(db, file_id)
    storage_path = Path(artifact.storage_path)
    try:
        content = storage_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="HTML artifact content is not valid UTF-8 text.",
        ) from exc

    return Response(content=content, media_type="text/html")


@router.get("/file/preview/artifact/{file_id}", name="preview_artifact_html")
async def preview_artifact_html(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    artifact = await _require_ready_html_artifact(db, file_id)
    content_url = request.url_for("artifact_html_content", file_id=file_id)
    title = escape(artifact.title or artifact.original_name or "HTML artifact preview")
    iframe_src = escape(str(content_url), quote=True)

    return HTMLResponse(
        content=f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      html, body {{
        margin: 0;
        width: 100%;
        height: 100%;
        background: #f8fafc;
      }}
      .preview-shell {{
        width: 100%;
        height: 100%;
        box-sizing: border-box;
        padding: 0;
      }}
      iframe {{
        width: 100%;
        height: 100%;
        border: 0;
        display: block;
        background: #ffffff;
      }}
    </style>
  </head>
  <body>
    <div class="preview-shell">
      <iframe
        src="{iframe_src}"
        title="{title}"
        sandbox="allow-scripts allow-modals"
        referrerpolicy="no-referrer"
      ></iframe>
    </div>
  </body>
</html>"""
    )


@router.get("/file/content/{file_id}", name="get_file_content")
async def get_file_content(
    file_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await download_file_resource("knowledge", file_id, db)


@router.get("/file/config/{file_kind}/{file_id}")
async def get_file_config(
    file_kind: FileKind,
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    file_record = await _get_file_record(db, file_kind=file_kind, file_id=file_id)
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{file_kind.title()} file {file_id} not found.",
        )

    extension = file_record.extension.lstrip(".").lower()
    if extension not in OfficePreviewExtensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Preview config is not supported for .{extension} files.",
        )

    file_url = _build_public_url(
        request,
        "download_file_resource",
        file_kind=file_kind,
        file_id=file_id,
    )
    callback_url = _build_public_url(request, "handle_callback")
    key_timestamp = int(file_record.updated_at.timestamp()) if file_record.updated_at else 0
    document_title = getattr(file_record, "original_name", Path(file_record.storage_path).name)

    return {
        "document": {
            "fileType": extension,
            "key": f"{file_kind}-{file_id}-{key_timestamp}",
            "title": document_title,
            "url": file_url,
        },
        "documentType": get_document_type(document_title),
        "editorConfig": {
            "lang": "zh",
            "mode": "view",
            "callbackUrl": callback_url,
        },
    }


@router.get("/file/config/{file_id}")
async def get_legacy_file_config(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await get_file_config("knowledge", file_id, request, db)


@router.post("/file/callback", name="handle_callback")
async def handle_callback(request: Request):
    body = await request.json()
    print(str(body))
    return {"error": 0}


def get_document_type(filename: str) -> str:
    ext = filename.split(".")[-1].lower()
    if ext in {"doc", "docx"}:
        return "word"
    if ext in {"xls", "xlsx"}:
        return "cell"
    if ext in {"ppt", "pptx"}:
        return "slide"
    if ext == "pdf":
        return "pdf"
    return ext
