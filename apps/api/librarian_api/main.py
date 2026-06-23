from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from librarian_api.config import settings
from librarian_chat.chat import ChatOptions, answer_question
from librarian_ingestion.embedding_ops import (
    EmbedQueryOptions,
    RebuildEmbeddingsOptions,
    embed_query,
    rebuild_embeddings,
)
from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_ingestion.scan import EpubSourceError
from librarian_logging import configure_logging
from librarian_metadata.genres import (
    DeleteBookGenresOptions,
    GenerateBookGenresOptions,
    ListBookGenresOptions,
    delete_book_genres,
    generate_book_genres,
    list_book_genres,
)
from librarian_search.search import SearchOptions, search_chunks
from librarian_storage.storage import create_ingestion_store
from librarian_summarization.summarize import SummarizeBookOptions, summarize_book

configure_logging()

app = FastAPI(title="Librarian API", version="0.1.0")


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
    enqueue_summaries: bool = False
    summary_generation_provider: Optional[str] = None
    summary_generation_model: Optional[str] = None
    summary_detail: str = "medium"


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


class SearchRequest(BaseModel):
    query: str
    database_url: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    limit: int = 10
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    author: Optional[str] = None


class ChatRequest(BaseModel):
    question: str
    database_url: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    retrieval_limit: int = 30
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    author: Optional[str] = None


class BookSummaryRequest(BaseModel):
    database_url: Optional[str] = None
    book_title: Optional[str] = None
    author: Optional[str] = None
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    detail: str = "medium"
    chunks_per_section: int = 8
    max_section_chars: int = 12000
    force_refresh: bool = False
    reset: bool = False
    include_chapter_summaries: bool = True
    chunk_summary_timeout_seconds: Optional[float] = None
    max_parallel_chunk_summaries: Optional[int] = None


class BookGenresRequest(BaseModel):
    database_url: Optional[str] = None
    source_summary_provider: Optional[str] = None
    source_summary_model: Optional[str] = None
    source_summary_detail: str = "medium"
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    max_secondary_genres: int = 3
    force_refresh: bool = False
    reset: bool = False


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
                enqueue_summaries=request.enqueue_summaries,
                summary_generation_provider=request.summary_generation_provider,
                summary_generation_model=request.summary_generation_model,
                summary_detail=request.summary_detail,
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


@app.get("/ingestion/status")
def ingestion_status(database_url: Optional[str] = None) -> dict[str, object]:
    resolved_database_url = database_url or settings.database_url
    try:
        store = create_ingestion_store(resolved_database_url)
    except (ValueError, NotImplementedError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    store.initialize()
    try:
        payload = asdict(store.get_ingestion_status())
        payload["database_url"] = resolved_database_url
        return payload
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


@app.post("/search")
def search_endpoint(request: SearchRequest) -> dict[str, object]:
    try:
        result = search_chunks(
            SearchOptions(
                query=request.query,
                database_url=request.database_url or settings.database_url,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                ollama_base_url=request.ollama_base_url,
                limit=request.limit,
                book_id=request.book_id,
                book_title=request.book_title,
                author=request.author,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/chat")
def chat_endpoint(request: ChatRequest) -> dict[str, object]:
    try:
        result = answer_question(
            ChatOptions(
                question=request.question,
                database_url=request.database_url or settings.database_url,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                generation_provider=request.generation_provider,
                generation_model=request.generation_model,
                ollama_base_url=request.ollama_base_url,
                retrieval_limit=request.retrieval_limit,
                book_id=request.book_id,
                book_title=request.book_title,
                author=request.author,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/books/{book_id}/summary")
def summarize_book_endpoint(
    book_id: str, request: BookSummaryRequest
) -> dict[str, object]:
    try:
        result = summarize_book(
            SummarizeBookOptions(
                database_url=request.database_url or settings.database_url,
                book_id=book_id,
                book_title=request.book_title,
                author=request.author,
                generation_provider=request.generation_provider,
                generation_model=request.generation_model,
                ollama_base_url=request.ollama_base_url,
                detail=request.detail,
                chunks_per_section=request.chunks_per_section,
                max_section_chars=request.max_section_chars,
                force_refresh=request.force_refresh,
                reset=request.reset,
                include_chapter_summaries=request.include_chapter_summaries,
                chunk_summary_timeout_seconds=request.chunk_summary_timeout_seconds,
                max_parallel_chunk_summaries=request.max_parallel_chunk_summaries,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/books/{book_id}/genres")
def generate_book_genres_endpoint(
    book_id: str, request: BookGenresRequest
) -> dict[str, object]:
    try:
        result = generate_book_genres(
            GenerateBookGenresOptions(
                database_url=request.database_url or settings.database_url,
                book_id=book_id,
                source_summary_provider=request.source_summary_provider,
                source_summary_model=request.source_summary_model,
                source_summary_detail=request.source_summary_detail,
                generation_provider=request.generation_provider,
                generation_model=request.generation_model,
                ollama_base_url=request.ollama_base_url,
                max_secondary_genres=request.max_secondary_genres,
                force_refresh=request.force_refresh,
                reset=request.reset,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.get("/books/{book_id}/genres")
def list_book_genres_endpoint(
    book_id: str,
    database_url: Optional[str] = None,
    genre_role: Optional[str] = None,
    source: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> list[dict[str, object]]:
    try:
        genres = list_book_genres(
            ListBookGenresOptions(
                database_url=database_url or settings.database_url,
                book_id=book_id,
                genre_role=genre_role,
                source=source,
                provider=provider,
                model=model,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return [asdict(genre) for genre in genres]


@app.delete("/books/{book_id}/genres")
def delete_book_genres_endpoint(
    book_id: str,
    database_url: Optional[str] = None,
    genre_role: Optional[str] = None,
    source: Optional[str] = "llm",
) -> dict[str, int]:
    try:
        deleted = delete_book_genres(
            DeleteBookGenresOptions(
                database_url=database_url or settings.database_url,
                book_id=book_id,
                genre_role=genre_role,
                source=source,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"deleted_genres": deleted}


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
