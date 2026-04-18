from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

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

DOCX_XML_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
TEXT_FILE_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")
SUPPORTED_TEXT_FILE_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
SUPPORTED_KNOWLEDGE_FILE_EXTENSIONS = {".pdf", ".docx", *SUPPORTED_TEXT_FILE_EXTENSIONS}


def normalize_knowledge_file_extension(extension: str | None) -> str:
    return (extension or "").strip().lower()


def supports_knowledge_file_extension(extension: str | None) -> bool:
    return normalize_knowledge_file_extension(extension) in SUPPORTED_KNOWLEDGE_FILE_EXTENSIONS


def _split_documents(documents: list[Document]) -> list[Document]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=250,
        chunk_overlap=20,
    )
    return text_splitter.split_documents(documents)


def _load_docx_document(file_path: str) -> list[Document]:
    path = Path(file_path)
    try:
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("word/document.xml")
    except KeyError as exc:
        raise ValueError(f"DOCX document.xml not found in {path.name}.") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid DOCX file: {path.name}.") from exc

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Unable to parse DOCX XML content: {path.name}.") from exc

    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", DOCX_XML_NAMESPACE):
        parts = [
            node.text
            for node in paragraph.findall(".//w:t", DOCX_XML_NAMESPACE)
            if node.text
        ]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)

    content = "\n".join(paragraphs).strip()
    if not content:
        raise ValueError(f"No readable text content found in DOCX file: {path.name}.")

    return [
        Document(
            page_content=content,
            metadata={"source": str(path)},
        )
    ]


def _read_text_file_content(file_path: str) -> str:
    path = Path(file_path)
    raw = path.read_bytes()
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _load_text_document(file_path: str) -> list[Document]:
    path = Path(file_path)
    content = _read_text_file_content(file_path).strip()
    if not content:
        raise ValueError(f"No readable text content found in text file: {path.name}.")

    return [
        Document(
            page_content=content,
            metadata={"source": str(path)},
        )
    ]


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
        extension = normalize_knowledge_file_extension(Path(file_path).suffix)
        if extension == ".pdf":
            loader = PyPDFLoader(file_path)
            return _split_documents(loader.load())
        if extension == ".docx":
            return _split_documents(_load_docx_document(file_path))
        if extension in SUPPORTED_TEXT_FILE_EXTENSIONS:
            return _split_documents(_load_text_document(file_path))
        raise ValueError(f"Unsupported extension for ingestion: {extension or 'unknown'}")

    def supports_file_extension(self, extension: str | None) -> bool:
        return supports_knowledge_file_extension(extension)

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
