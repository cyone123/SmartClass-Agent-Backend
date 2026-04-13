import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file_ingestion import FileIngestionRuntime, get_file_ingestion_runtime
from app.core.rag import RagRuntime, get_rag_runtime
from app.dependencies.db import get_db
from app.schemas.file import (
    AttachmentFileResponse,
    KnowledgeFileListResponse,
    KnowledgeFileResponse,
)
from app.schemas.response import success_response
from app.services import file_service

router = APIRouter()

JWT_SECRET = "Szn90fT3cXjWNS9ZYMN5XsiVEmd1qREM"


@router.get("/file/knowledgeFile", response_model=KnowledgeFileListResponse)
async def list_knowledge_files(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeFileListResponse:
    files = await file_service.list_files_by_plan(db, plan_id)
    return success_response(data=files, response_model=KnowledgeFileListResponse)


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


@router.get("/file/content/{file_id}", name="get_file_content")
async def get_file_content(
    file_id: int,
    db: AsyncSession = Depends(get_db),
):
    file_record = await file_service.get_file_by_id(db, file_id)
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found.",
        )
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file content not found.",
        )
    return FileResponse(
        path=storage_path,
        media_type=file_record.mime_type,
        filename=file_record.original_name,
    )


@router.get("/file/config/{file_id}")
async def get_file_config(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    file_record = await file_service.get_file_by_id(db, file_id)
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found.",
        )

    file_url = str(request.url_for("get_file_content", file_id=file_id))
    callback_url = str(request.url_for("handle_callback"))

    config = {
        "document": {
            "fileType": file_record.extension.lstrip("."),
            "key": str(int(time.time() * 1000)),
            "title": file_record.original_name,
            "url": file_url,
        },
        "documentType": get_document_type(file_record.original_name),
        "editorConfig": {
            "lang": "zh",
            "mode": "edit",
            "callbackUrl": callback_url,
        },
    }

    # token = jwt.encode(config, JWT_SECRET, algorithm="HS256")
    # config["token"] = token
    return config


@router.post("/file/callback", name="handle_callback")
async def handle_callback(request: Request):
    body = await request.json()
    print(str(body))
    return {"error": 0}


def get_document_type(file_id: str):
    ext = file_id.split(".")[-1].lower()
    if ext in ["doc", "docx", "html"]:
        return "word"
    elif ext in ["xls", "xlsx"]:
        return "cell"
    elif ext in ["ppt", "pptx"]:
        return "slide"
    elif ext in ["pdf"]:
        return "pdf"
    else:
        return ext
