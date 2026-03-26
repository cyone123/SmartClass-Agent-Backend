import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_db_uri
from app.models import Base


class PostgresProvider:
    _checkpoint_lock: asyncio.Lock | None = None
    _checkpoint_pool: AsyncConnectionPool | None = None
    _checkpoint_saver: AsyncPostgresSaver | None = None

    @staticmethod
    def get_db_conn_string() -> str:
        return get_db_uri()

    @classmethod
    def get_checkpoint_lock(cls) -> asyncio.Lock:
        if cls._checkpoint_lock is None:
            cls._checkpoint_lock = asyncio.Lock()
        return cls._checkpoint_lock

    @classmethod
    async def init_agent_checkpointer(cls) -> AsyncPostgresSaver:
        if cls._checkpoint_saver is not None:
            return cls._checkpoint_saver

        async with cls.get_checkpoint_lock():
            if cls._checkpoint_saver is None:
                pool = AsyncConnectionPool(
                    conninfo=cls.get_db_conn_string(),
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                        "row_factory": dict_row,
                    },
                    min_size=4,
                    max_size=20,
                    open=False,
                    name="langgraph-checkpoint-pool",
                )
                await pool.open(wait=True)

                saver = AsyncPostgresSaver(conn=pool)
                await saver.setup()

                cls._checkpoint_pool = pool
                cls._checkpoint_saver = saver

        return cls._checkpoint_saver

    @classmethod
    def get_agent_checkpointer(cls) -> AsyncPostgresSaver:
        if cls._checkpoint_saver is None:
            raise RuntimeError("Agent checkpointer is not initialized.")
        return cls._checkpoint_saver

    @classmethod
    async def close_agent_resources(cls) -> None:
        async with cls.get_checkpoint_lock():
            pool = cls._checkpoint_pool
            cls._checkpoint_pool = None
            cls._checkpoint_saver = None

        if pool is not None:
            await pool.close()


def get_agent_checkpointer() -> AsyncPostgresSaver:
    return PostgresProvider.get_agent_checkpointer()


async def init_agent_checkpointer() -> AsyncPostgresSaver:
    return await PostgresProvider.init_agent_checkpointer()


def get_async_db_uri() -> str:
    uri = PostgresProvider.get_db_conn_string()
    if uri.startswith("postgresql://"):
        return "postgresql+asyncpg://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+asyncpg://" + uri[len("postgres://") :]
    raise ValueError(f"Unsupported database URI scheme in {uri}")


async_engine = create_async_engine(
    get_async_db_uri(),
    echo=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_agent_checkpointer() -> None:
    await PostgresProvider.close_agent_resources()


async def close_db_resources() -> None:
    await async_engine.dispose()
