import asyncio
import sys

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.file import router as file_router
from app.api.plan import router as plan_router
from app.api.session import router as session_router
from app.core.agent import create_agent_runtime
from app.core.file_ingestion import FileIngestionRuntime
from app.core.rag import create_rag_runtime
from app.core.speech import create_speech_runtime
from app.core.skills import create_skill_registry
from app.core.video_transcribe import create_video_transcription_runtime
from app.dependencies.db import close_db_resources, init_db

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent_runtime = None
    file_ingestion_runtime = None
    rag_runtime = None
    skill_registry = None
    speech_runtime = None
    video_transcription_runtime = None
    try:
        await init_db()
        skill_registry = create_skill_registry()
        app.state.skill_registry = skill_registry
        rag_runtime = await create_rag_runtime()
        app.state.rag_runtime = rag_runtime
        speech_runtime = create_speech_runtime()
        app.state.speech_runtime = speech_runtime
        video_transcription_runtime = create_video_transcription_runtime(
            speech_runtime=speech_runtime,
        )
        app.state.video_transcription_runtime = video_transcription_runtime
        file_ingestion_runtime = FileIngestionRuntime(rag_runtime)
        await file_ingestion_runtime.start()
        app.state.file_ingestion_runtime = file_ingestion_runtime
        agent_runtime = await create_agent_runtime(
            rag_runtime,
            skill_registry=skill_registry,
            video_transcription_runtime=video_transcription_runtime,
        )
        app.state.agent_runtime = agent_runtime
        yield
    finally:
        if agent_runtime is not None:
            await agent_runtime.close()
        if file_ingestion_runtime is not None:
            await file_ingestion_runtime.stop()
        if rag_runtime is not None:
            await rag_runtime.close()
        await close_db_resources()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(file_router, prefix="/api")
app.include_router(plan_router, prefix="/api")
app.include_router(session_router, prefix="/api")
