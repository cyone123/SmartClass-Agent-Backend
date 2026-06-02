import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_db_uri
from app.models import Base


class PostgresProvider:
    _checkpoint_lock: asyncio.Lock | None = None
    _checkpoint_pool: AsyncConnectionPool | None = None
    _checkpoint_saver: AsyncPostgresSaver | None = None
    _memory_lock: asyncio.Lock | None = None
    _memory_pool: AsyncConnectionPool | None = None
    _memory_store: AsyncPostgresStore | None = None

    @staticmethod
    def get_db_conn_string() -> str:
        return get_db_uri()

    @classmethod
    def get_checkpoint_lock(cls) -> asyncio.Lock:
        if cls._checkpoint_lock is None:
            cls._checkpoint_lock = asyncio.Lock()
        return cls._checkpoint_lock

    @classmethod
    def get_memory_lock(cls) -> asyncio.Lock:
        if cls._memory_lock is None:
            cls._memory_lock = asyncio.Lock()
        return cls._memory_lock

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
    async def init_memory_store(cls) -> AsyncPostgresStore:
        if cls._memory_store is not None:
            return cls._memory_store

        async with cls.get_memory_lock():
            if cls._memory_store is None:
                pool = AsyncConnectionPool(
                    conninfo=cls.get_db_conn_string(),
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                        "row_factory": dict_row,
                    },
                    min_size=2,
                    max_size=10,
                    open=False,
                    name="langgraph-memory-store-pool",
                )
                await pool.open(wait=True)

                store = AsyncPostgresStore(conn=pool)
                await store.setup()

                cls._memory_pool = pool
                cls._memory_store = store

        return cls._memory_store

    @classmethod
    def get_memory_store(cls) -> AsyncPostgresStore:
        if cls._memory_store is None:
            raise RuntimeError("Memory store is not initialized.")
        return cls._memory_store

    @classmethod
    async def close_agent_resources(cls) -> None:
        async with cls.get_checkpoint_lock():
            pool = cls._checkpoint_pool
            cls._checkpoint_pool = None
            cls._checkpoint_saver = None

        if pool is not None:
            await pool.close()

        async with cls.get_memory_lock():
            memory_pool = cls._memory_pool
            cls._memory_pool = None
            cls._memory_store = None

        if memory_pool is not None:
            await memory_pool.close()


def get_agent_checkpointer() -> AsyncPostgresSaver:
    return PostgresProvider.get_agent_checkpointer()


async def init_agent_checkpointer() -> AsyncPostgresSaver:
    return await PostgresProvider.init_agent_checkpointer()


def get_memory_store() -> AsyncPostgresStore:
    return PostgresProvider.get_memory_store()


async def init_memory_store() -> AsyncPostgresStore:
    return await PostgresProvider.init_memory_store()


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
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS knowledge_files
                ADD COLUMN IF NOT EXISTS storage_backend VARCHAR(32) NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS knowledge_files
                ADD COLUMN IF NOT EXISTS storage_key VARCHAR(1024) NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS teaching_plans
                ADD COLUMN IF NOT EXISTS user_id INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS teaching_sessions
                ADD COLUMN IF NOT EXISTS user_id INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS knowledge_files
                ADD COLUMN IF NOT EXISTS user_id INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS attachment_files
                ADD COLUMN IF NOT EXISTS user_id INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS artifact_files
                ADD COLUMN IF NOT EXISTS user_id INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_users_username
                ON users (username)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_teaching_plans_user_id
                ON teaching_plans (user_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_teaching_sessions_user_id
                ON teaching_sessions (user_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_knowledge_files_user_id
                ON knowledge_files (user_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_attachment_files_user_id
                ON attachment_files (user_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_artifact_files_user_id
                ON artifact_files (user_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_knowledge_files_storage_backend
                ON knowledge_files (storage_backend)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_knowledge_files_storage_key
                ON knowledge_files (storage_key)
                """
            )
        )

    from app.services.auth_service import ensure_default_admin

    async with AsyncSessionLocal() as session:
        admin = await ensure_default_admin(session)
        await session.execute(text("UPDATE teaching_plans SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": admin.id})
        await session.execute(text("UPDATE teaching_sessions SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": admin.id})
        await session.execute(text("UPDATE knowledge_files SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": admin.id})
        await session.execute(text("UPDATE attachment_files SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": admin.id})
        await session.execute(text("UPDATE artifact_files SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": admin.id})
        await session.commit()


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
