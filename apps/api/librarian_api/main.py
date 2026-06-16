from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from librarian_api.config import settings
from librarian_ingestion.embedding_ops import (
    EmbedQueryOptions,
    RebuildEmbeddingsOptions,
    embed_query,
    rebuild_embeddings,
)
from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_ingestion.scan import EpubSourceError
from librarian_ingestion.storage import create_ingestion_store

app = FastAPI(title="Librarian", version="0.1.0")


class IngestionRunRequest(BaseModel):
    books_dir: Optional[str] = None
    database_url: Optional[str] = None
    force: bool = False
    list_epubs: bool = False
    embed_chunks: bool = False
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    embedding_batch_size: int = 16


class RebuildEmbeddingsRequest(BaseModel):
    database_url: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    batch_size: int = 16
    chunk_page_size: int = 500
    reset: bool = False
    reset_all: bool = False


class EmbedQueryRequest(BaseModel):
    query: str
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "books_dir": settings.books_dir,
        "host_books_dir": settings.host_books_dir,
        "codex_broker_enabled": settings.enable_codex_broker,
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Librarian",
        "message": "Local-first EPUB RAG workspace is ready.",
    }


@app.post("/ingestion/run")
def run_ingestion_endpoint(request: IngestionRunRequest) -> dict[str, object]:
    try:
        result = run_ingestion(
            IngestionOptions(
                books_dir=request.books_dir or settings.books_dir,
                database_url=request.database_url or settings.database_url,
                force=request.force,
                list_epubs=request.list_epubs,
                embed_chunks=request.embed_chunks,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                ollama_base_url=request.ollama_base_url,
                embedding_batch_size=request.embedding_batch_size,
            )
        )
    except (EpubSourceError, ValueError, NotImplementedError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.get("/ingestion/summary")
def ingestion_summary(database_url: Optional[str] = None) -> dict[str, object]:
    try:
        store = create_ingestion_store(database_url or settings.database_url)
    except (ValueError, NotImplementedError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    store.initialize()
    try:
        return asdict(store.get_summary())
    finally:
        store.close()


@app.post("/embeddings/rebuild")
def rebuild_embeddings_endpoint(request: RebuildEmbeddingsRequest) -> dict[str, object]:
    try:
        result = rebuild_embeddings(
            RebuildEmbeddingsOptions(
                database_url=request.database_url or settings.database_url,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                ollama_base_url=request.ollama_base_url,
                batch_size=request.batch_size,
                chunk_page_size=request.chunk_page_size,
                reset=request.reset,
                reset_all=request.reset_all,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/embeddings/query")
def embed_query_endpoint(request: EmbedQueryRequest) -> dict[str, object]:
    try:
        result = embed_query(
            EmbedQueryOptions(
                query=request.query,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                ollama_base_url=request.ollama_base_url,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.get("/books")
def list_books(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    database_url: Optional[str] = None,
) -> list[dict[str, object]]:
    try:
        store = create_ingestion_store(database_url or settings.database_url)
    except (ValueError, NotImplementedError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    store.initialize()
    try:
        return [
            asdict(book)
            for book in store.list_books(status=status, limit=limit, offset=offset)
        ]
    finally:
        store.close()
