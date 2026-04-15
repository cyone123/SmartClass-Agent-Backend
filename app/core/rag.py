from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import Request
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import Column, PGEngine, PGVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text

from app.dependencies.db import async_engine

load_dotenv()


class RagRuntime:
    def __init__(self, async_engine, *, table_name: str = "vector_store") -> None:
        self.pg_engine = PGEngine.from_engine(engine=async_engine)
        self.async_engine = async_engine
        self.table_name = table_name
        self.metadata_columns = [
            Column(name="plan_id", data_type="INTEGER", nullable=False),
            Column(name="file_id", data_type="INTEGER", nullable=False),
            Column(name="source_name", data_type="TEXT", nullable=True),
            Column(name="chunk_index", data_type="INTEGER", nullable=True),
            Column(name="page", data_type="INTEGER", nullable=True),
        ]
        self.embedding_model = OpenAIEmbeddings(
            model=os.getenv("EMBEDDINGS_MODEL"),
            api_key=os.getenv("EMBEDDINGS_API_KEY"),
            base_url=os.getenv("EMBEDDINGS_BASE_URL"),
            check_embedding_ctx_length=False,
        )
        self.vector_store: PGVectorStore | None = None
        self.vector_size: int | None = None

    async def _vector_table_exists(self) -> bool:
        query = text("SELECT to_regclass(:table_name)")
        async with self.async_engine.connect() as conn:
            result = await conn.execute(query, {"table_name": f"public.{self.table_name}"})
            return result.scalar_one_or_none() is not None

    async def init_vector_store(self) -> RagRuntime:
        if self.vector_size is None:
            # probe_vector = await self.embedding_model.aembed_query("vector size probe")
            self.vector_size = 3072

        if not await self._vector_table_exists():
            await self.pg_engine.ainit_vectorstore_table(
                table_name=self.table_name,
                vector_size=self.vector_size,
                metadata_columns=self.metadata_columns,
            )
        self.vector_store = await PGVectorStore.create(
            engine=self.pg_engine,
            table_name=self.table_name,
            embedding_service=self.embedding_model,
            metadata_columns=[column.name for column in self.metadata_columns],
        )
        return self

    async def load_and_split_file(self, file_path: str) -> list[Document]:
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=250,
            chunk_overlap=20,
        )
        return text_splitter.split_documents(documents) 

    def _get_vector_store(self) -> PGVectorStore:
        if self.vector_store is None:
            raise RuntimeError("RAG vector store is not initialized.")
        return self.vector_store

    async def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        vector_store = self._get_vector_store()
        await vector_store.aadd_texts(texts, metadatas=metadatas)

    async def add_documents(self, documents: list[Document]) -> None:
        vector_store = self._get_vector_store()
        await vector_store.aadd_documents(documents)

    async def retrieval(
        self,
        query: str,
        *,
        plan_id: int | None = None,
        k: int = 2,
    ) -> list[Document]:
        vector_store = self._get_vector_store()
        filter_clause = {"plan_id": plan_id} if plan_id is not None else None
        return await vector_store.asimilarity_search(query, k=k, filter=filter_clause)

    async def delete_by_file_id(self, file_id: int) -> None:
        vector_store = self._get_vector_store()
        await vector_store.adelete(filter={"file_id": file_id})

    async def close(self) -> None:
        return None


async def create_rag_runtime() -> RagRuntime:
    runtime = RagRuntime(async_engine=async_engine)
    await runtime.init_vector_store()
    return runtime


def get_rag_runtime(request: Request) -> RagRuntime:
    runtime = getattr(request.app.state, "rag_runtime", None)
    if runtime is None:
        raise RuntimeError("RAG runtime is not initialized.")
    return runtime
