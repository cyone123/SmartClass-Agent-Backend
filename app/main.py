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
from app.core.rag import create_rag_runtime
from app.dependencies.db import close_db_resources, init_db

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent_runtime = None
    rag_runtime = None
    try:
        await init_db()
        rag_runtime = await create_rag_runtime()
        app.state.rag_runtime = rag_runtime
        agent_runtime = await create_agent_runtime(rag_runtime)
        app.state.agent_runtime = agent_runtime
        yield
    finally:
        if agent_runtime is not None:
            await agent_runtime.close()
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
