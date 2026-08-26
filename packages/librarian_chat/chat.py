from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
import re
from time import perf_counter

from librarian_chat.generation import (
    ChatMessage,
    create_configured_generator,
)
from librarian_config.config import (
    resolve_chat_retrieval_backend,
    resolve_generation_answer_capability,
)
from librarian_ingestion.embedding_ops import (
    EmbedQueryOptions,
    EmbedQueryResult,
    embed_query,
)
from librarian_search.hybrid import HybridSearchOptions, hybrid_search_chunks
from librarian_search.opensearch import OpenSearchError
from librarian_search.search import (
    SearchOptions,
    SearchResponse,
    SearchResult,
    search_chunks,
)


logger = logging.getLogger(__name__)


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")
_LOOKUP_QUESTION_PREFIXES = ("what", "who", "when", "where", "which")
_QUESTION_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
    }
)


@dataclass(frozen=True)
class ChatOptions:
    question: str
    database_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    answer_capability: str | None = None
    ollama_base_url: str | None = None
    retrieval_limit: int = 30
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class ChatSource:
    source_id: str
    score: float
    chunk_id: str
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    chunk_index: int
    text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ChatTimings:
    """Wall-clock timings for the visible stages of one chat request."""

    query_embedding_seconds: float = 0.0
    retrieval_seconds: float = 0.0
    prompt_construction_seconds: float = 0.0
    generation_seconds: float = 0.0
    total_seconds: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class ChatResponse:
    question: str
    answer: str
    embedding_provider: str
    embedding_model: str
    generation_provider: str
    generation_model: str
    retrieval_limit: int
    candidate_count: int
    filters: dict[str, str]
    sources: list[ChatSource]
    answer_capability: str = "quality"
    retrieval_backend: str = "sqlite"
    timings: ChatTimings = field(default_factory=ChatTimings)

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.answer,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "generation_provider": self.generation_provider,
            "generation_model": self.generation_model,
            "retrieval_limit": self.retrieval_limit,
            "candidate_count": self.candidate_count,
            "filters": self.filters,
            "answer_capability": self.answer_capability,
            "retrieval_backend": self.retrieval_backend,
            "timings": self.timings.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
        }


def answer_question(options: ChatOptions) -> ChatResponse:
    total_started = perf_counter()
    question = options.question.strip()
    if not question:
        raise ValueError("question must not be empty")

    answer_capability = resolve_generation_answer_capability(
        answer_capability=options.answer_capability,
        generation_provider=options.generation_provider,
        generation_model=options.generation_model,
    )

    retrieval_limit = max(1, options.retrieval_limit)
    embedding_started = perf_counter()
    query_embedding = embed_query(
        EmbedQueryOptions(
            query=question,
            embedding_provider=options.embedding_provider,
            embedding_model=options.embedding_model,
            ollama_base_url=options.ollama_base_url,
        )
    )
    query_embedding_seconds = perf_counter() - embedding_started

    retrieval_started = perf_counter()
    search_response, retrieval_backend = _retrieve_sources(
        options,
        query_embedding=query_embedding,
        retrieval_limit=retrieval_limit,
    )
    retrieval_seconds = perf_counter() - retrieval_started
    sources = _to_sources(search_response.results)

    prompt_started = perf_counter()
    messages = _build_messages(question, sources)
    prompt_construction_seconds = perf_counter() - prompt_started

    generation_started = perf_counter()
    generator = create_configured_generator(
        provider=options.generation_provider,
        model=options.generation_model,
        ollama_base_url=options.ollama_base_url,
    )
    answer = (
        _lightweight_lookup_answer(question, sources)
        if answer_capability == "lightweight"
        else None
    )
    if answer is None:
        answer = generator.generate(messages)
    generation_seconds = perf_counter() - generation_started

    return ChatResponse(
        question=question,
        answer=answer,
        embedding_provider=search_response.embedding_provider,
        embedding_model=search_response.embedding_model,
        generation_provider=generator.provider,
        generation_model=generator.model,
        retrieval_limit=retrieval_limit,
        candidate_count=search_response.candidate_count,
        filters=search_response.filters,
        sources=sources,
        answer_capability=answer_capability,
        retrieval_backend=retrieval_backend,
        timings=ChatTimings(
            query_embedding_seconds=query_embedding_seconds,
            retrieval_seconds=retrieval_seconds,
            prompt_construction_seconds=prompt_construction_seconds,
            generation_seconds=generation_seconds,
            total_seconds=perf_counter() - total_started,
        ),
    )


def _retrieve_sources(
    options: ChatOptions,
    *,
    query_embedding: EmbedQueryResult,
    retrieval_limit: int,
) -> tuple[SearchResponse, str]:
    """Prefer OpenSearch hybrid retrieval and keep SQLite as a safe fallback.

    ``auto`` uses the rebuildable OpenSearch projection whenever it can serve
    the configured index. A missing, unavailable, or otherwise unhealthy
    projection falls back to SQLite's source-of-truth embeddings. Explicit
    ``opensearch`` configuration intentionally surfaces its error instead of
    silently changing the selected backend; explicit ``sqlite`` skips the
    projection entirely.
    """
    backend = resolve_chat_retrieval_backend()
    if backend in {"auto", "opensearch"}:
        try:
            return (
                hybrid_search_chunks(
                    HybridSearchOptions(
                        query=query_embedding.query,
                        embedding_provider=options.embedding_provider,
                        embedding_model=options.embedding_model,
                        ollama_base_url=options.ollama_base_url,
                        limit=retrieval_limit,
                        book_id=options.book_id,
                        book_title=options.book_title,
                        author=options.author,
                        query_embedding=query_embedding,
                    )
                ),
                "opensearch",
            )
        except OpenSearchError as error:
            if backend == "opensearch":
                raise
            logger.info(
                "OpenSearch chat retrieval unavailable; using SQLite fallback: %s",
                error,
            )

    return (
        search_chunks(
            SearchOptions(
                query=query_embedding.query,
                database_url=options.database_url,
                embedding_provider=options.embedding_provider,
                embedding_model=options.embedding_model,
                ollama_base_url=options.ollama_base_url,
                limit=retrieval_limit,
                book_id=options.book_id,
                book_title=options.book_title,
                author=options.author,
                query_embedding=query_embedding,
            )
        ),
        "sqlite",
    )


def _to_sources(results: list[SearchResult]) -> list[ChatSource]:
    sources: list[ChatSource] = []
    for index, result in enumerate(results, start=1):
        sources.append(
            ChatSource(
                source_id=f"S{index}",
                score=result.score,
                chunk_id=result.chunk_id,
                book_id=result.book_id,
                relative_path=result.relative_path,
                title=result.title,
                authors=result.authors,
                chunk_index=result.chunk_index,
                text=result.text,
            )
        )
    return sources


def _build_messages(question: str, sources: list[ChatSource]) -> list[ChatMessage]:
    source_text = _format_sources(sources)
    return [
        ChatMessage(
            role="system",
            content=(
                "You are Librarian, a local reading assistant. Answer only from "
                "the provided source chunks. If the chunks do not support an "
                "answer, say that the local library context is insufficient. "
                "Cite source IDs like [S1] when using a source."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Question:\n{question}\n\n"
                f"Source chunks:\n{source_text}\n\n"
                "Write a concise answer grounded in the source chunks."
            ),
        ),
    ]


def _format_sources(sources: list[ChatSource]) -> str:
    if not sources:
        return "No source chunks were retrieved."

    formatted: list[str] = []
    for source in sources:
        title = source.title or source.relative_path
        authors = ", ".join(source.authors) if source.authors else "Unknown author"
        formatted.append(
            "\n".join(
                [
                    f"[{source.source_id}] {title} by {authors}",
                    f"Path: {source.relative_path}",
                    f"Chunk: {source.chunk_index}",
                    f"Text: {source.text}",
                ]
            )
        )
    return "\n\n".join(formatted)


def _lightweight_lookup_answer(question: str, sources: list[ChatSource]) -> str | None:
    """Return an exact local sentence for a well-supported lookup question.

    The default Compose model is intentionally small. For a short factual
    lookup, preserving the source's subject/action relationship is more useful
    than asking that model to paraphrase adjacent sentences. This path is
    deliberately narrow: it only applies when a question-led source sentence
    covers the request's meaningful terms. Broader questions still use the
    configured generator.
    """
    question_terms = _meaningful_terms(question)
    if not _is_lookup_question(question) or not question_terms:
        return None

    best: tuple[float, int, ChatSource, str] | None = None
    for source in sources:
        for sentence in _sentences(source.text):
            sentence_terms = _meaningful_terms(sentence)
            overlap = len(question_terms & sentence_terms)
            coverage = overlap / len(question_terms)
            candidate = (coverage, overlap, source, sentence)
            if best is None or candidate[:2] > best[:2]:
                best = candidate

    if best is None:
        return None
    coverage, overlap, source, sentence = best
    required_overlap = 1 if len(question_terms) == 1 else 2
    if overlap < required_overlap or coverage < 0.5:
        return None
    return f"{sentence} [{source.source_id}]"


def _is_lookup_question(question: str) -> bool:
    first_word = ""
    if question.strip():
        first_word = question.lstrip().split(maxsplit=1)[0].casefold().rstrip("?:")
    return first_word in _LOOKUP_QUESTION_PREFIXES or question.casefold().startswith(
        ("how many", "how much")
    )


def _meaningful_terms(value: str) -> set[str]:
    return {
        term
        for term in _WORD.findall(value.casefold())
        if term not in _QUESTION_STOP_WORDS and len(term) > 1
    }


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for line in text.splitlines()
        for sentence in _SENTENCE_BOUNDARY.split(line.strip())
        if sentence.strip()
    ]
