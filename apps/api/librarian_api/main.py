from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from librarian_chat.chat import (
    ChatOptions,
    answer_question,
    prepare_answer_question,
    stream_answer_question,
)
from librarian_config.config import (
    get_librarian_config,
    resolve_chunk_summary_timeout_seconds,
    resolve_embedding_model,
    resolve_embedding_provider,
    resolve_generation_answer_capability,
)
from librarian_contracts.broker_limits import DEFAULT_OUTER_DEADLINE_SECONDS
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
from librarian_recommendations.recommendations import (
    RecommendationOptions,
    recommend_books,
)
from librarian_search.hybrid import HybridSearchOptions, hybrid_search_chunks
from librarian_search.opensearch import OpenSearchIndexOptions, index_chunks
from librarian_search.search import SearchOptions, search_chunks
from librarian_storage.storage import create_ingestion_store
from librarian_summarization.summarize import SummarizeBookOptions, summarize_book
from pydantic import BaseModel, Field

from librarian_api.config import get_settings
from librarian_api.r2_chat import R2ApiChatCaller, _RequestContext
from librarian_answer_adapters.grpc_generation import R2GenerationDeadlineExceeded

configure_logging(file_enabled=False)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(log_file=settings.log_file)
    r2_caller: R2ApiChatCaller | None = None
    config = get_librarian_config()
    if config.uses_r2_api_runtime:
        # The authenticated capability handshake completes before FastAPI
        # accepts browser traffic.  The caller owns this one channel/stub for
        # the complete process lifetime; it never falls back to broker HTTP.
        r2_caller = await R2ApiChatCaller.open(model_id=config.generation.model)
        _app.state.r2_api_chat_caller = r2_caller
    store = create_ingestion_store(settings.database_url)
    try:
        try:
            store.initialize()
        finally:
            store.close()
        yield
    finally:
        if r2_caller is not None:
            await r2_caller.close()
            del _app.state.r2_api_chat_caller


app = FastAPI(title="Librarian API", version="0.1.0", lifespan=lifespan)


class IngestionRunRequest(BaseModel):
    books_dir: Optional[str] = None
    database_url: Optional[str] = None
    force: bool = False
    reprocess_unchanged: bool = Field(
        default=False,
        description=(
            "Deliberately re-parse unchanged EPUBs to apply updated parsing or "
            "content-classification rules. This can take as long as a full "
            "library ingestion."
        ),
    )
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
    include_non_content: bool = Field(
        default=False,
        description="Include publisher, catalog, and other non-body EPUB content.",
    )


class HybridSearchRequest(BaseModel):
    query: str
    opensearch_url: Optional[str] = None
    index_name: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    limit: int = 10
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    author: Optional[str] = None
    include_non_content: bool = Field(
        default=False,
        description="Include publisher, catalog, and other non-body EPUB content.",
    )
    genre: Optional[str] = None
    tag: Optional[str] = None


class SearchIndexRequest(BaseModel):
    database_url: Optional[str] = None
    opensearch_url: Optional[str] = None
    index_name: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    batch_size: int = Field(default=250, ge=1)
    reset: bool = False


class ChatRequest(BaseModel):
    """Request one source-faithful chat answer from the configured local library."""

    question: str
    database_url: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
    answer_capability: Optional[Literal["quality", "lightweight"]] = Field(
        default=None,
        description=(
            "Required when generation_provider or generation_model changes the "
            "JSON-configured generator. Otherwise the JSON generation capability "
            "is used."
        ),
    )
    ollama_base_url: Optional[str] = None
    retrieval_limit: int = 30
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    author: Optional[str] = None
    include_non_content: bool = Field(
        default=False,
        description=(
            "Include publisher, catalog, and other non-body EPUB content. "
            "Publication and edition questions enable this automatically."
        ),
    )


class ChatSourceResponse(BaseModel):
    """A local chunk supplied as evidence for a chat answer."""

    source_id: str
    score: float
    chunk_id: str
    book_id: str
    relative_path: str
    title: Optional[str] = None
    authors: list[str]
    chunk_index: int = Field(ge=0)
    content_type: Literal["body", "front_matter", "back_matter"] = "body"
    text: str


class ChatTimingsResponse(BaseModel):
    """Stage timings reported for a completed synchronous chat request."""

    query_embedding_seconds: float = Field(ge=0)
    retrieval_seconds: float = Field(ge=0)
    prompt_construction_seconds: float = Field(ge=0)
    generation_seconds: float = Field(ge=0)
    total_seconds: float = Field(ge=0)


class ErrorResponse(BaseModel):
    """Intentional error payload returned for a rejected API operation."""

    detail: str


class ChatResponse(BaseModel):
    """The documented response contract for one ``POST /chat`` request."""

    question: str
    answer: str
    embedding_provider: str
    embedding_model: str
    generation_provider: str
    generation_model: str
    answer_capability: Literal["quality", "lightweight"] = Field(
        description=(
            "Capability resolved for this request: the explicit request value "
            "for an overridden generator, or the configured JSON default."
        )
    )
    retrieval_limit: int = Field(ge=1)
    candidate_count: int = Field(ge=0)
    filters: dict[str, str]
    retrieval_backend: Literal["opensearch", "sqlite"] = Field(
        description=(
            "Backend that supplied sources for this response. Auto retrieval "
            "uses OpenSearch when its configured index is available and falls "
            "back to SQLite otherwise."
        )
    )
    timings: ChatTimingsResponse = Field(
        description="Wall-clock seconds spent in each synchronous chat stage."
    )
    minimum_citation_count: int = Field(ge=1)
    citation_count: int = Field(ge=0)
    outcome: Literal["answered", "insufficient_evidence", "generation_unavailable"]
    sources: list[ChatSourceResponse]


_CHAT_BAD_REQUEST_RESPONSE = {
    "model": ErrorResponse,
    "description": (
        "Invalid or unsupported chat provider/model configuration, missing "
        "answer capability for an override."
    ),
}


class RecommendationRequest(BaseModel):
    query: str
    database_url: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    limit: int = 5
    retrieval_limit: int = 40
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    tag: Optional[str] = None


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
    settings = get_settings()
    return {
        "status": "ok",
        "books_dir": settings.books_dir,
        "host_books_dir": settings.host_books_dir,
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
                books_dir=request.books_dir or get_settings().books_dir,
                database_url=request.database_url or get_settings().database_url,
                force=request.force or request.reprocess_unchanged,
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
        store = create_ingestion_store(database_url or get_settings().database_url)
    except (ValueError, NotImplementedError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    store.initialize()
    try:
        return asdict(store.get_summary())
    finally:
        store.close()


@app.get("/ingestion/status")
def ingestion_status(database_url: Optional[str] = None) -> dict[str, object]:
    resolved_database_url = database_url or get_settings().database_url
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
                database_url=request.database_url or get_settings().database_url,
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
                database_url=request.database_url or get_settings().database_url,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                ollama_base_url=request.ollama_base_url,
                limit=request.limit,
                book_id=request.book_id,
                book_title=request.book_title,
                author=request.author,
                include_non_content=request.include_non_content,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/search/hybrid")
def hybrid_search_endpoint(request: HybridSearchRequest) -> dict[str, object]:
    try:
        result = hybrid_search_chunks(
            HybridSearchOptions(
                query=request.query,
                opensearch_url=request.opensearch_url,
                index_name=request.index_name,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                ollama_base_url=request.ollama_base_url,
                limit=request.limit,
                book_id=request.book_id,
                book_title=request.book_title,
                author=request.author,
                include_non_content=request.include_non_content,
                genre=request.genre,
                tag=request.tag,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/search/index")
def index_search_endpoint(request: SearchIndexRequest) -> dict[str, object]:
    """Rebuild or incrementally update the OpenSearch retrieval index."""
    try:
        result = index_chunks(
            OpenSearchIndexOptions(
                database_url=request.database_url or get_settings().database_url,
                opensearch_url=request.opensearch_url,
                index_name=request.index_name,
                embedding_provider=resolve_embedding_provider(
                    request.embedding_provider
                ),
                embedding_model=resolve_embedding_model(request.embedding_model),
                batch_size=request.batch_size,
                reset=request.reset,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post(
    "/chat",
    response_model=ChatResponse,
    response_description="Source-faithful answer and the local source chunks cited as evidence.",
    responses={400: _CHAT_BAD_REQUEST_RESPONSE},
)
async def chat_endpoint(payload: ChatRequest, request: Request) -> dict[str, object]:
    try:
        caller = getattr(app.state, "r2_api_chat_caller", None)
        options = _chat_options(payload)
        if caller is None:
            result = answer_question(options)
        else:
            caller.validate_options(options)
            context = _RequestContext(is_disconnected=request.is_disconnected)
            context.start()
            try:
                result = await caller.answer(options, context=context)
            finally:
                await context.close()
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post(
    "/chat/stream",
    response_class=StreamingResponse,
    response_description=(
        "Server-sent events: source-validated retrieval metadata, exact cited "
        "source-sentence tokens, then one terminal completion."
    ),
    responses={
        200: {
            "description": "A text/event-stream response. See docs/api-endpoints.md for event payloads.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        400: _CHAT_BAD_REQUEST_RESPONSE,
    },
)
async def chat_stream_endpoint(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Stream exact cited source sentences without changing the JSON API."""
    caller = getattr(app.state, "r2_api_chat_caller", None)
    if caller is not None:
        try:
            options = _chat_options(payload)
            caller.validate_options(options)
        except (ValueError, NotImplementedError, RuntimeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        async def r2_event_bytes():
            context = _RequestContext(is_disconnected=request.is_disconnected)
            context.start()
            try:
                async for event in caller.stream(options, context=context):
                    encoded = json.dumps(event.data, separators=(",", ":"))
                    yield f"event: {event.event}\ndata: {encoded}\n\n".encode("utf-8")
            finally:
                await context.close()

        return StreamingResponse(
            r2_event_bytes(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        preparation = prepare_answer_question(_chat_options(payload))
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    def event_bytes():
        for event in stream_answer_question(preparation):
            payload = json.dumps(event.data, separators=(",", ":"))
            yield f"event: {event.event}\ndata: {payload}\n\n".encode("utf-8")

    return StreamingResponse(
        event_bytes(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chat_options(request: ChatRequest) -> ChatOptions:
    """Map both chat transports through one override/capability boundary."""
    return ChatOptions(
        question=request.question,
        database_url=request.database_url or get_settings().database_url,
        embedding_provider=request.embedding_provider,
        embedding_model=request.embedding_model,
        generation_provider=request.generation_provider,
        generation_model=request.generation_model,
        answer_capability=resolve_generation_answer_capability(
            answer_capability=request.answer_capability,
            generation_provider=request.generation_provider,
            generation_model=request.generation_model,
        ),
        answer_capability_is_override=request.answer_capability is not None,
        ollama_base_url=request.ollama_base_url,
        retrieval_limit=request.retrieval_limit,
        book_id=request.book_id,
        book_title=request.book_title,
        author=request.author,
        include_non_content=request.include_non_content,
    )


@app.post("/recommendations")
async def recommendations_endpoint(request: RecommendationRequest, http_request: Request) -> dict[str, object]:
    try:
        options = RecommendationOptions(
            query=request.query,
            database_url=request.database_url or get_settings().database_url,
            embedding_provider=request.embedding_provider,
            embedding_model=request.embedding_model,
            generation_provider=request.generation_provider,
            generation_model=request.generation_model,
            ollama_base_url=request.ollama_base_url,
            limit=request.limit,
            retrieval_limit=request.retrieval_limit,
            book_id=request.book_id,
            book_title=request.book_title,
            author=request.author,
            genre=request.genre,
            tag=request.tag,
        )
        caller = getattr(app.state, "r2_api_chat_caller", None)
        if caller is None:
            result = recommend_books(options)
        else:
            result = await _run_r2_generation(
                caller.recommend_books,
                options,
                http_request,
            )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/books/{book_id}/summary")
async def summarize_book_endpoint(
    book_id: str, request: BookSummaryRequest, http_request: Request
) -> dict[str, object]:
    try:
        options = SummarizeBookOptions(
            database_url=request.database_url or get_settings().database_url,
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
        caller = getattr(app.state, "r2_api_chat_caller", None)
        if caller is None:
            result = summarize_book(options)
        else:
            result = await _run_r2_generation(
                caller.summarize_book,
                options,
                http_request,
                deadline_seconds=_r2_summary_deadline(
                    request.chunk_summary_timeout_seconds
                ),
            )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


@app.post("/books/{book_id}/genres")
async def generate_book_genres_endpoint(
    book_id: str, request: BookGenresRequest, http_request: Request
) -> dict[str, object]:
    try:
        options = GenerateBookGenresOptions(
            database_url=request.database_url or get_settings().database_url,
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
        caller = getattr(app.state, "r2_api_chat_caller", None)
        if caller is None:
            result = generate_book_genres(options)
        else:
            result = await _run_r2_generation(
                caller.generate_book_genres,
                options,
                http_request,
            )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result.to_dict()


async def _run_r2_generation(
    operation,
    options,
    http_request: Request,
    *,
    deadline_seconds: float = 30.0,
):
    """Run one R2 API operation without treating a browser abort as an error.

    The generated-client adapter cancels the in-flight RPC when this context is
    cancelled.  A disconnected browser has no response to receive, so expose a
    quiet 499 terminal response instead of letting ``CancelledError`` escape
    FastAPI and create an ASGI error traceback.  Server task cancellation is
    still propagated normally.
    """

    context = _RequestContext(
        deadline_seconds=deadline_seconds,
        is_disconnected=http_request.is_disconnected,
    )
    context.start()
    try:
        return await operation(options, context=context)
    except R2GenerationDeadlineExceeded as error:
        raise HTTPException(status_code=504, detail="generation deadline elapsed") from error
    except asyncio.CancelledError as error:
        if context.was_disconnected:
            raise HTTPException(status_code=499, detail="client disconnected") from error
        if context.is_cancelled():
            raise HTTPException(status_code=504, detail="generation deadline elapsed") from error
        raise
    finally:
        await context.close()


def _r2_summary_deadline(configured_timeout: float | None) -> float:
    """Cap the complete R2 summary request at the broker's outer deadline."""

    return min(
        resolve_chunk_summary_timeout_seconds(configured_timeout),
        DEFAULT_OUTER_DEADLINE_SECONDS,
    )


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
                database_url=database_url or get_settings().database_url,
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
                database_url=database_url or get_settings().database_url,
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
        store = create_ingestion_store(database_url or get_settings().database_url)
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
