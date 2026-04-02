from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import Request

from app.core.rag import RagRuntime
from app.dependencies.db import AsyncSessionLocal
from app.services import file_service


class FileIngestionRuntime:
    def __init__(self, rag_runtime: RagRuntime) -> None:
        self.rag_runtime = rag_runtime
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        await self._recover_pending_files()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker_task
        self._worker_task = None

    async def enqueue(self, file_id: int) -> None:
        await self._queue.put(file_id)

    async def _recover_pending_files(self) -> None:
        async with AsyncSessionLocal() as db:
            file_ids = await file_service.get_recoverable_file_ids(db)
        for file_id in file_ids:
            await self.enqueue(file_id)

    async def _worker_loop(self) -> None:
        while True:
            file_id = await self._queue.get()
            try:
                async with AsyncSessionLocal() as db:
                    await file_service.process_file_ingestion(
                        db,
                        file_id=file_id,
                        rag_runtime=self.rag_runtime,
                    )
            except Exception as exc:
                print(f"【文件入库】file_id={file_id} processing failed: {exc}")
            finally:
                self._queue.task_done()


def get_file_ingestion_runtime(request: Request) -> FileIngestionRuntime:
    runtime = getattr(request.app.state, "file_ingestion_runtime", None)
    if runtime is None:
        raise RuntimeError("File ingestion runtime is not initialized.")
    return runtime
