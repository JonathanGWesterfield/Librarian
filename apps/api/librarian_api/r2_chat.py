"""R2 API grounded-chat composition over one process-owned gRPC client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic, perf_counter
from typing import Awaitable, Callable
from uuid import uuid4

from librarian_answer import AnswerRequest, AnswerRuntime, AnswerScope, EvidenceSnapshot
from librarian_answer_adapters.grpc_broker import GeneratedGrpcBrokerClient
from librarian_answer_adapters.grpc_chat import GrpcChatOperations
from librarian_answer_adapters.grpc_generation import GrpcGenerationGenerator
from librarian_answer_adapters.legacy import LegacySentenceEvidenceRetriever
from librarian_answer_adapters.r2_startup import open_r2_client
from librarian_chat import chat as chat_module
from librarian_chat.chat import (
    ChatOptions,
    ChatResponse,
    ChatSource,
    ChatStreamEvent,
    ChatTimings,
    retrieve_chat_evidence,
)
from librarian_config.config import resolve_database_url
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_metadata.genres import GenerateBookGenresOptions, generate_book_genres
from librarian_recommendations.recommendations import RecommendationOptions, recommend_books
from librarian_storage.storage import create_ingestion_store
from librarian_summarization.summarize import SummarizeBookOptions, summarize_book

_R2_ANSWER_DEADLINE_SECONDS = 30.0
_R2_SELECTOR_DEADLINE_SECONDS = 10.0


@dataclass
class R2ApiChatCaller:
    """One ready generated client and the three API-chat operation adapters."""

    client: GeneratedGrpcBrokerClient
    operations: GrpcChatOperations

    @classmethod
    async def open(cls, *, model_id: str) -> R2ApiChatCaller:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("gRPC chat operations require a model ID")
        client = await open_r2_client(expected_principal="api")
        try:
            return cls(client=client, operations=GrpcChatOperations(client, model_id))
        except Exception:
            await client.close()
            raise

    async def close(self) -> None:
        """Close the process-owned gRPC channel during API shutdown."""

        await self.client.close()

    def validate_options(self, options: ChatOptions) -> None:
        """Reject all request-level generation identity overrides in R2."""

        if (
            options.generation_provider is not None
            or options.generation_model is not None
            or options.answer_capability_is_override
        ):
            raise ValueError("R2 chat does not allow per-request generation overrides")

    def validate_generation_options(
        self,
        *,
        generation_provider: str | None,
        generation_model: str | None,
        ollama_base_url: str | None,
    ) -> None:
        """Keep the R2 API's actual broker identity authoritative."""

        if any(
            value is not None
            for value in (generation_provider, generation_model, ollama_base_url)
        ):
            raise ValueError("R2 generation does not allow per-request generation overrides")

    async def summarize_book(
        self,
        options: SummarizeBookOptions,
        *,
        context: _RequestContext,
    ):
        """Run local summary caching with chapter/book provider work over gRPC."""

        self.validate_generation_options(
            generation_provider=options.generation_provider,
            generation_model=options.generation_model,
            ollama_base_url=options.ollama_base_url,
        )
        return await asyncio.to_thread(
            summarize_book,
            options,
            generator=self._generation_generator(
                context, default_operation=delivery_pb2.BOOK_SUMMARIZATION
            ),
        )

    async def generate_book_genres(
        self,
        options: GenerateBookGenresOptions,
        *,
        context: _RequestContext,
    ):
        """Run local genre storage with its JSON generation through gRPC."""

        self.validate_generation_options(
            generation_provider=options.generation_provider,
            generation_model=options.generation_model,
            ollama_base_url=options.ollama_base_url,
        )
        return await asyncio.to_thread(
            generate_book_genres,
            options,
            generator=self._generation_generator(
                context, default_operation=delivery_pb2.GENRE_GENERATION
            ),
        )

    async def recommend_books(
        self,
        options: RecommendationOptions,
        *,
        context: _RequestContext,
    ):
        """Run local ranking with recommendation prose through gRPC."""

        self.validate_generation_options(
            generation_provider=options.generation_provider,
            generation_model=options.generation_model,
            ollama_base_url=options.ollama_base_url,
        )
        return await asyncio.to_thread(
            recommend_books,
            options,
            generator=self._generation_generator(
                context, default_operation=delivery_pb2.RECOMMENDATION_SYNTHESIS
            ),
        )

    def _generation_generator(
        self, context: _RequestContext, *, default_operation: int
    ) -> GrpcGenerationGenerator:
        return GrpcGenerationGenerator(
            client=self.client,
            model=self.operations.model_id,
            event_loop=asyncio.get_running_loop(),
            context=context,
            default_operation=default_operation,
        )

    async def answer(
        self,
        options: ChatOptions,
        *,
        context: _RequestContext | None = None,
    ) -> ChatResponse:
        """Run retrieval locally and all chat generation through generated RPCs."""

        self.validate_options(options)
        owned_context = context is None
        context = context or _RequestContext()
        try:
            retrieved = await _retrieve_chat_evidence_with_context(options, context)
            if context.is_cancelled():
                raise asyncio.CancelledError("R2 chat was cancelled during retrieval")
            started = retrieved.total_started
            question = retrieved.question
            answer_capability = retrieved.answer_capability
            required_sources = retrieved.required_sources
            retrieval_limit = retrieved.retrieval_limit
            search_response = retrieved.search_response
            retrieval_backend = retrieved.retrieval_backend
            sources = retrieved.sources
            evidence_sufficient = retrieved.evidence_sufficient
            publication_question = retrieved.publication_question
            query_embedding_seconds = retrieved.query_embedding_seconds
            retrieval_seconds = retrieved.retrieval_seconds

            if not evidence_sufficient:
                return self._response(
                    question=question,
                    answer=chat_module._insufficient_evidence_answer(
                        publication_question=publication_question,
                        required_sources=required_sources,
                        scope=search_response.filters,
                    ),
                    sources=[],
                    answer_capability=answer_capability,
                    retrieval_limit=retrieval_limit,
                    search_response=search_response,
                    retrieval_backend=retrieval_backend,
                    required_sources=required_sources,
                    query_embedding_seconds=query_embedding_seconds,
                    retrieval_seconds=retrieval_seconds,
                    generation_seconds=0.0,
                    total_started=started,
                    outcome="insufficient_evidence",
                )

            generation_started = perf_counter()
            store_factory = lambda: create_ingestion_store(resolve_database_url(options.database_url))
            evidence = LegacySentenceEvidenceRetriever(
                question=question,
                sources=sources,
                required_sources=required_sources,
                store_factory=store_factory,
                retrieval_backend=retrieval_backend,
            )
            runtime = AnswerRuntime(
                evidence_retriever=_R2EvidenceRetriever(evidence, self.operations),
                generation_broker=self.operations.synthesis_broker(),
                support_reviewer=self.operations,
            )
            result = await runtime.collect(
                AnswerRequest(
                    request_id=str(uuid4()),
                    question=question,
                    scope=AnswerScope(
                        book_id=search_response.filters.get("book_id"),
                        book_title=search_response.filters.get("book_title"),
                        author=search_response.filters.get("author"),
                    ),
                    minimum_citation_count=required_sources,
                ),
                context,
            )
            generation_seconds = perf_counter() - generation_started
            if result is None:
                if context.is_cancelled():
                    raise asyncio.CancelledError("R2 chat was cancelled before a terminal result")
                raise RuntimeError("R2 chat ended without a terminal result")
            selected = []
            for citation in result.citations:
                source = evidence.source_for_candidate(citation.candidate_id)
                if source is not None and source.chunk_id not in {item.chunk_id for item in selected}:
                    selected.append(source)
            answer = result.answer
            if result.outcome == "answered":
                answer = f"{answer} {' '.join(f'[{source.source_id}]' for source in selected)}".strip()
            else:
                selected = []
            return self._response(
                question=question,
                answer=answer,
                sources=selected,
                answer_capability=answer_capability,
                retrieval_limit=retrieval_limit,
                search_response=search_response,
                retrieval_backend=retrieval_backend,
                required_sources=required_sources,
                query_embedding_seconds=query_embedding_seconds,
                retrieval_seconds=retrieval_seconds,
                generation_seconds=generation_seconds,
                total_started=started,
                outcome=result.outcome,
            )
        finally:
            if owned_context:
                await context.close()

    async def stream(
        self, options: ChatOptions, *, context: _RequestContext
    ):
        """Adapt a buffered R2 answer to the established R0 SSE event contract."""

        started = perf_counter()
        try:
            result = await self.answer(options, context=context)
        except asyncio.CancelledError:
            return
        if context.is_cancelled():
            return

        time_to_first_event = perf_counter() - started
        response = result.to_dict()
        retrieval = dict(response)
        retrieval.pop("answer", None)
        retrieval["timings"] = {
            "query_embedding_seconds": result.timings.query_embedding_seconds,
            "retrieval_seconds": result.timings.retrieval_seconds,
            "prompt_construction_seconds": result.timings.prompt_construction_seconds,
            "time_to_first_event_seconds": time_to_first_event,
        }
        yield ChatStreamEvent("retrieval", retrieval)

        if context.is_cancelled():
            return
        time_to_first_token = perf_counter() - started
        yield ChatStreamEvent("token", {"text": result.answer})

        if context.is_cancelled():
            return
        completed = dict(response)
        timings = dict(result.timings.to_dict())
        timings["time_to_first_event_seconds"] = time_to_first_event
        timings["time_to_first_token_seconds"] = time_to_first_token
        completed["timings"] = timings
        yield ChatStreamEvent("complete", completed)

    def _response(
        self,
        *,
        question: str,
        answer: str,
        sources: list[ChatSource],
        answer_capability: str,
        retrieval_limit: int,
        search_response: object,
        retrieval_backend: str,
        required_sources: int,
        query_embedding_seconds: float,
        retrieval_seconds: float,
        generation_seconds: float,
        total_started: float,
        outcome: str,
    ) -> ChatResponse:
        return ChatResponse(
            question=question,
            answer=answer,
            embedding_provider=search_response.embedding_provider,
            embedding_model=search_response.embedding_model,
            generation_provider="grpc",
            generation_model=self.operations.model_id,
            retrieval_limit=retrieval_limit,
            candidate_count=search_response.candidate_count,
            filters=search_response.filters,
            sources=sources,
            answer_capability=answer_capability,
            retrieval_backend=retrieval_backend,
            minimum_citation_count=required_sources,
            outcome=outcome,
            timings=ChatTimings(
                query_embedding_seconds=query_embedding_seconds,
                retrieval_seconds=retrieval_seconds,
                generation_seconds=generation_seconds,
                total_seconds=perf_counter() - total_started,
            ),
        )


@dataclass(frozen=True)
class _R2EvidenceRetriever:
    """Run the required source-selection RPC before grounded synthesis."""

    legacy: LegacySentenceEvidenceRetriever
    operations: GrpcChatOperations

    async def retrieve(
        self, request: AnswerRequest, context: object
    ) -> tuple[EvidenceSnapshot, ...]:
        evidence = self.legacy.retrieve(request, context)
        selection_context = _PhaseRequestContext(
            parent=context,
            deadline_at=monotonic() + _R2_SELECTOR_DEADLINE_SECONDS,
        )
        try:
            return await self.operations.select_sources(
                question=request.question,
                evidence=evidence,
                minimum_citation_count=request.minimum_citation_count,
                request_id=request.request_id,
                context=selection_context,
            ) or ()
        except asyncio.CancelledError:
            if context.is_cancelled():
                raise
            # The selector has its own 10-second cap. Its timeout is a safe
            # no-selection result, while a browser/parent cancellation aborts
            # the whole answer without a late terminal frame.
            return ()

    def reload_source(self, *, book_id: str, chunk_id: str):
        return self.legacy.reload_source(book_id=book_id, chunk_id=chunk_id)


class _RequestContext:
    """One 30-second API budget with optional browser-disconnect propagation."""

    def __init__(
        self,
        *,
        deadline_seconds: float = _R2_ANSWER_DEADLINE_SECONDS,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._deadline_at = monotonic() + deadline_seconds
        self._cancelled = asyncio.Event()
        self._disconnected = False
        self._is_disconnected = is_disconnected
        self._watcher: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Watch a FastAPI request without coupling the runtime to HTTP types."""

        if self._is_disconnected is not None and self._watcher is None:
            self._watcher = asyncio.create_task(self._watch_disconnect())

    async def close(self) -> None:
        """Stop a request-scoped watcher once the endpoint has finished."""

        if self._watcher is not None:
            self._watcher.cancel()
            try:
                await self._watcher
            except asyncio.CancelledError:
                pass
            self._watcher = None

    async def _watch_disconnect(self) -> None:
        assert self._is_disconnected is not None
        while not self.is_cancelled():
            if await self._is_disconnected():
                self._disconnected = True
                self._cancelled.set()
                return
            await asyncio.sleep(0.05)

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set() or monotonic() >= self._deadline_at

    @property
    def was_disconnected(self) -> bool:
        """Whether the browser, rather than a server deadline, ended this request."""

        return self._disconnected

    def remaining_seconds(self) -> float | None:
        if self._cancelled.is_set():
            return 0.0
        return max(0.0, self._deadline_at - monotonic())


@dataclass(frozen=True)
class _PhaseRequestContext:
    """A bounded operation view over the parent request's cancellation state."""

    parent: object
    deadline_at: float

    def is_cancelled(self) -> bool:
        return self.parent.is_cancelled() or monotonic() >= self.deadline_at

    def remaining_seconds(self) -> float | None:
        parent_remaining = self.parent.remaining_seconds()
        phase_remaining = max(0.0, self.deadline_at - monotonic())
        return (
            phase_remaining
            if parent_remaining is None
            else min(phase_remaining, parent_remaining)
        )


async def _retrieve_chat_evidence_with_context(
    options: ChatOptions, context: _RequestContext
):
    """Run legacy retrieval off-loop while retaining API cancellation semantics."""

    task = asyncio.create_task(asyncio.to_thread(retrieve_chat_evidence, options))
    try:
        while not task.done():
            if context.is_cancelled():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise asyncio.CancelledError("R2 chat was cancelled during retrieval")
            remaining = context.remaining_seconds()
            await asyncio.wait(
                {task},
                timeout=min(0.05, remaining) if remaining is not None else 0.05,
            )
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
