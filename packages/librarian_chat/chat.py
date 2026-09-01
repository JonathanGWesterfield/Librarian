from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
import json
import logging
import re
from time import perf_counter

from librarian_chat.generation import (
    ChatMessage,
    GenerationError,
    Generator,
    create_configured_generator,
    create_generator,
)
from librarian_config.config import (
    LibrarianConfigError,
    get_librarian_config,
    resolve_database_url,
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
from librarian_storage.storage import create_ingestion_store


logger = logging.getLogger(__name__)


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")
_AUTHOR_VIEW_TERMS = frozenset(
    {
        "argue",
        "argues",
        "believe",
        "believes",
        "opinion",
        "position",
        "say",
        "says",
        "teach",
        "teaches",
        "think",
        "thinks",
        "view",
        "views",
        "write",
        "writes",
    }
)
_BROAD_QUESTION_TERMS = (
    "about",
    "overview",
    "theme",
    "themes",
    "what does the author",
    "what do the author",
)
_EVENT_QUESTION_PREFIXES = (
    "what happened",
    "what happens",
    "what occurred",
)
_EVENT_FOLLOWUP_MARKER = re.compile(
    r"\b(?:after|afterward|immediately|next|then|following)\b"
)
_PUBLICATION_METADATA_TERMS = (
    "copyright",
    "edition",
    "isbn",
    "publication",
    "published",
    "publishing",
    "publisher",
    "table of contents",
)
_PUBLISHER_ENTITY_QUESTION = re.compile(
    r"\b(?:who|which|what)\b[^?]*\bpublisher\b"
    r"|\bname\b[^?]*\bpublisher\b"
    r"|\b(?:who|which)\s+published\b"
)
_EXPLICIT_PUBLISHER_EVIDENCE = re.compile(r"\bpublisher\s*:\s*|\bpublished\s+by\b")
_PUBLICATION_DATE_EVIDENCE = re.compile(
    r"\b(?:published|publication)\b(?:\s+[\w-]+){0,5}[\s,:-]+"
    r"(?:1[5-9]\d{2}|20\d{2}|21\d{2})\b"
)
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
    include_non_content: bool = False


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
    content_type: str = "body"

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


@dataclass(frozen=True)
class PreparedChat:
    """Evidence-validated chat work shared by JSON and streaming responses.

    Preparation intentionally performs the query embedding and retrieval once.
    The two HTTP contracts then differ only in how they deliver generation.
    """

    total_started: float
    question: str
    generator: Generator
    answer_capability: str
    retrieval_limit: int
    required_sources: int
    embedding_provider: str
    embedding_model: str
    candidate_count: int
    filters: dict[str, str]
    sources: list[ChatSource]
    retrieval_backend: str
    query_embedding_seconds: float
    retrieval_seconds: float
    prompt_construction_seconds: float
    immediate_answer: str | None
    grounded_tokens: list[str] = field(default_factory=list)

    def retrieval_event(
        self,
        sources: list[ChatSource] | None = None,
        *,
        time_to_first_event_seconds: float | None = None,
    ) -> dict[str, object]:
        """Return safe metadata after all evidence guards have run."""
        event_sources = self.sources if sources is None else sources
        timings: dict[str, float] = {
            "query_embedding_seconds": self.query_embedding_seconds,
            "retrieval_seconds": self.retrieval_seconds,
            "prompt_construction_seconds": self.prompt_construction_seconds,
        }
        if time_to_first_event_seconds is not None:
            timings["time_to_first_event_seconds"] = time_to_first_event_seconds
        return {
            "question": self.question,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "generation_provider": self.generator.provider,
            "generation_model": self.generator.model,
            "answer_capability": self.answer_capability,
            "retrieval_limit": self.retrieval_limit,
            "candidate_count": self.candidate_count,
            "filters": self.filters,
            "retrieval_backend": self.retrieval_backend,
            "sources": [source.to_dict() for source in event_sources],
            "timings": timings,
        }


@dataclass(frozen=True)
class ChatStreamEvent:
    """One transport-neutral event in a prepared chat stream."""

    event: str
    data: dict[str, object]


@dataclass(frozen=True)
class _SourceSentenceCandidate:
    """One exact sentence that a trusted selector may choose, but never edit."""

    sentence_id: str
    source: ChatSource
    sentence: str


def prepare_answer_question(options: ChatOptions) -> PreparedChat:
    """Retrieve and validate evidence once before choosing a delivery mode."""
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
    effective_author = _effective_author_scope(options, question)
    include_non_content = options.include_non_content or _asks_for_publication_metadata(
        question
    )
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
        author=effective_author,
        include_non_content=include_non_content,
    )
    retrieval_seconds = perf_counter() - retrieval_started
    publication_question = _asks_for_publication_metadata(question)
    retrieval_results = search_response.results
    if publication_question:
        retrieval_results = [
            result
            for result in retrieval_results
            if _is_publication_evidence(question, result.content_type, result.text)
        ]
    sources = _to_sources(retrieval_results)
    required_sources = _required_source_count(question, effective_author)
    evidence_sufficient = _has_sufficient_evidence(
        sources,
        required_sources=required_sources,
    )
    if not evidence_sufficient:
        # Results that fail the guard are diagnostics, not answer evidence.
        # Preserve candidate_count and timings, but never display misleading
        # citations alongside an insufficiency response.
        sources = []

    # Preserve the timing field for existing API clients. The chat path does
    # not build a generation prompt because it never asks a model to rewrite
    # the source evidence.
    prompt_construction_seconds = 0.0

    generator = create_configured_generator(
        provider=options.generation_provider,
        model=options.generation_model,
        ollama_base_url=options.ollama_base_url,
    )
    immediate_answer: str | None = None
    grounded_tokens: list[str] = []
    if not evidence_sufficient:
        immediate_answer = _insufficient_evidence_answer(
            publication_question=publication_question,
            required_sources=required_sources,
        )
    else:
        grounded_answer = _semantic_source_selection_answer(
            question,
            sources,
            required_sources=required_sources,
            answer_capability=answer_capability,
            generator=generator,
        )
        if grounded_answer is None:
            grounded_answer = _grounded_extractive_answer(
                question,
                sources,
                required_sources=required_sources,
            )
        if grounded_answer is None:
            # Retrieval candidates without a directly relevant source
            # sentence are diagnostics, not answer evidence. This applies to
            # every configured provider and capability: no model may alter or
            # invent a claim from those chunks.
            sources = []
            immediate_answer = _insufficient_evidence_answer(
                publication_question=publication_question,
                required_sources=required_sources,
            )
        else:
            sources, grounded_tokens = grounded_answer
            immediate_answer = "\n\n".join(grounded_tokens)
    preparation = PreparedChat(
        total_started=total_started,
        question=question,
        generator=generator,
        answer_capability=answer_capability,
        retrieval_limit=retrieval_limit,
        required_sources=required_sources,
        embedding_provider=search_response.embedding_provider,
        embedding_model=search_response.embedding_model,
        candidate_count=search_response.candidate_count,
        filters=search_response.filters,
        sources=sources,
        retrieval_backend=retrieval_backend,
        query_embedding_seconds=query_embedding_seconds,
        retrieval_seconds=retrieval_seconds,
        prompt_construction_seconds=prompt_construction_seconds,
        immediate_answer=immediate_answer,
        grounded_tokens=grounded_tokens,
    )
    return preparation


def answer_question(options: ChatOptions) -> ChatResponse:
    """Return a complete response assembled only from cited source sentences."""
    preparation = prepare_answer_question(options)
    generation_started = perf_counter()
    # ``prepare_answer_question`` chooses either extractive evidence or an
    # insufficiency response. Keeping this route model-free prevents the JSON
    # endpoint from making claims that the streaming endpoint would withhold.
    answer = preparation.immediate_answer
    if answer is None:  # Defensive guard for future preparation changes.
        raise RuntimeError("prepared chat did not contain a grounded answer")
    generation_seconds = perf_counter() - generation_started

    return _response_from_preparation(
        preparation,
        answer=answer,
        generation_seconds=generation_seconds,
    )


def stream_answer_question(preparation: PreparedChat) -> Iterator[ChatStreamEvent]:
    """Stream the same exact source sentences returned by the JSON contract."""
    generation_started = perf_counter()
    first_event_seconds: float | None = None
    first_token_seconds: float | None = None
    response_sources = preparation.sources
    retrieval_emitted = False

    def emit_retrieval(sources: list[ChatSource]) -> ChatStreamEvent:
        nonlocal first_event_seconds, retrieval_emitted
        if first_event_seconds is None:
            first_event_seconds = perf_counter() - preparation.total_started
        retrieval_emitted = True
        return ChatStreamEvent(
            "retrieval",
            preparation.retrieval_event(
                sources,
                time_to_first_event_seconds=first_event_seconds,
            ),
        )

    try:
        # Retrieval is already evidence-floor validated by preparation, so it
        # is useful and safe progress in its own right. Emit it before native
        # generation: the UI can show the grounded passages while strict
        # sentence verification continues to withhold answer text.
        yield emit_retrieval(response_sources)
        answer = preparation.immediate_answer
        if answer is None:  # Defensive guard for future preparation changes.
            raise RuntimeError("prepared chat did not contain a grounded answer")
        for index, token in enumerate(preparation.grounded_tokens):
            if first_token_seconds is None:
                first_token_seconds = perf_counter() - preparation.total_started
            text = token if index == 0 else f"\n\n{token}"
            yield ChatStreamEvent("token", {"text": text})

        response = _response_from_preparation(
            preparation,
            answer=answer,
            generation_seconds=perf_counter() - generation_started,
            sources=response_sources,
        )
        completed = response.to_dict()
        timings = dict(response.timings.to_dict())
        timings["time_to_first_event_seconds"] = first_event_seconds
        timings["time_to_first_token_seconds"] = first_token_seconds
        completed["timings"] = timings
        yield ChatStreamEvent("complete", completed)
    except (GenerationError, RuntimeError, ValueError, NotImplementedError) as error:
        if not retrieval_emitted:
            yield emit_retrieval(response_sources)
        yield ChatStreamEvent(
            "error",
            {
                "detail": str(error),
                "timings": {
                    "generation_seconds": perf_counter() - generation_started,
                    "total_seconds": perf_counter() - preparation.total_started,
                    "time_to_first_event_seconds": first_event_seconds,
                    "time_to_first_token_seconds": first_token_seconds,
                },
            },
        )


def _response_from_preparation(
    preparation: PreparedChat,
    *,
    answer: str,
    generation_seconds: float,
    sources: list[ChatSource] | None = None,
) -> ChatResponse:
    """Build the existing JSON response shape from shared prepared evidence."""

    return ChatResponse(
        question=preparation.question,
        answer=answer,
        embedding_provider=preparation.embedding_provider,
        embedding_model=preparation.embedding_model,
        generation_provider=preparation.generator.provider,
        generation_model=preparation.generator.model,
        retrieval_limit=preparation.retrieval_limit,
        candidate_count=preparation.candidate_count,
        filters=preparation.filters,
        sources=preparation.sources if sources is None else sources,
        answer_capability=preparation.answer_capability,
        retrieval_backend=preparation.retrieval_backend,
        timings=ChatTimings(
            query_embedding_seconds=preparation.query_embedding_seconds,
            retrieval_seconds=preparation.retrieval_seconds,
            prompt_construction_seconds=preparation.prompt_construction_seconds,
            generation_seconds=generation_seconds,
            total_seconds=perf_counter() - preparation.total_started,
        ),
    )


def _retrieve_sources(
    options: ChatOptions,
    *,
    query_embedding: EmbedQueryResult,
    retrieval_limit: int,
    author: str | None,
    include_non_content: bool,
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
                        author=author,
                        include_non_content=include_non_content,
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
                author=author,
                include_non_content=include_non_content,
                query_embedding=query_embedding,
            )
        ),
        "sqlite",
    )


def _effective_author_scope(options: ChatOptions, question: str) -> str | None:
    """Respect direct scope, otherwise apply only an unambiguous named author.

    A question such as ``What does C.S. Lewis say ...`` should not mix every
    author in a whole-library search.  Generic "the author" questions remain
    unscoped because there is no safe author to infer.
    """
    if options.author or options.book_id or options.book_title:
        return options.author
    if not _asks_for_author_view(question):
        return None

    store = create_ingestion_store(resolve_database_url(options.database_url))
    store.initialize()
    try:
        authors: set[str] = set()
        offset = 0
        while True:
            books = store.list_books(status="ingested", limit=500, offset=offset)
            authors.update(
                author.strip()
                for book in books
                for author in book.authors
                if author.strip()
            )
            if len(books) < 500:
                break
            offset += len(books)
    finally:
        store.close()

    normalized_question = _author_identity(question)
    matches: dict[str, set[str]] = {}
    for author in authors:
        identity = _author_identity(author)
        # One short name such as "Lee" is too easy to match accidentally.
        if len(identity) < 5 or identity not in normalized_question:
            continue
        matches.setdefault(identity, set()).add(author)

    if len(matches) != 1:
        return None
    names = next(iter(matches.values()))
    return next(iter(names)) if len(names) == 1 else None


def _author_identity(value: str) -> str:
    return "".join(_WORD.findall(value.casefold()))


def _asks_for_author_view(question: str) -> bool:
    terms = _meaningful_terms(question)
    return bool(terms & _AUTHOR_VIEW_TERMS)


def _asks_for_publication_metadata(question: str) -> bool:
    normalized = " ".join(question.casefold().split())
    return any(term in normalized for term in _PUBLICATION_METADATA_TERMS)


def _asks_for_publisher_entity(question: str) -> bool:
    """Identify questions that require a publisher name rather than a date."""
    normalized = " ".join(question.casefold().split())
    return bool(_PUBLISHER_ENTITY_QUESTION.search(normalized))


def _asks_for_publication_date(question: str) -> bool:
    """Identify publication questions whose answer may be a date."""
    normalized = " ".join(question.casefold().split())
    if "publish" not in normalized and "publication" not in normalized:
        return False
    return (
        normalized.startswith("when ")
        or "what year" in normalized
        or "which year" in normalized
        or "publication date" in normalized
    )


def _required_source_count(question: str, author: str | None) -> int:
    """Set an evidence floor before a broad synthesis reaches generation."""
    normalized = " ".join(question.casefold().split())
    if author and _asks_for_author_view(question):
        return 10
    if any(term in normalized for term in _BROAD_QUESTION_TERMS):
        return 10
    return 1


def _has_sufficient_evidence(
    sources: list[ChatSource], *, required_sources: int
) -> bool:
    distinct_sources = {source.chunk_id for source in sources}
    if len(distinct_sources) < required_sources:
        return False
    # Negative-only cosine candidates mean there was no semantically useful
    # match. OpenSearch scores are non-negative, so this leaves normal hybrid
    # retrieval unaffected while protecting the SQLite fallback from noise.
    return max(source.score for source in sources) >= 0.05


def _insufficient_evidence_answer(
    *, publication_question: bool, required_sources: int
) -> str:
    if publication_question:
        return (
            "I could not find publication or edition evidence in the local EPUB "
            "content to answer that reliably."
        )
    if required_sources > 1:
        return (
            "I could not find enough distinct body-text passages to answer that "
            "broad question reliably. Try narrowing the question or selecting a book."
        )
    return "I could not find enough relevant body-text evidence to answer that reliably."


def _is_publication_evidence(
    question: str,
    content_type: str,
    text: str,
) -> bool:
    """Require publisher questions to cite the relevant non-body EPUB text."""
    if content_type == "body":
        return False
    normalized_question = " ".join(question.casefold().split())
    normalized_text = " ".join(text.casefold().split())
    if "isbn" in normalized_question:
        return "isbn" in normalized_text
    if "copyright" in normalized_question:
        return "copyright" in normalized_text
    if "edition" in normalized_question:
        return "edition" in normalized_text
    if _asks_for_publisher_entity(question):
        return bool(_EXPLICIT_PUBLISHER_EVIDENCE.search(normalized_text))
    if _asks_for_publication_date(question):
        return bool(_PUBLICATION_DATE_EVIDENCE.search(normalized_text))
    if "publish" in normalized_question:
        return "published" in normalized_text or "publisher" in normalized_text
    if "table of contents" in normalized_question:
        return "contents" in normalized_text
    return True


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
                content_type=result.content_type,
                text=result.text,
            )
        )
    return sources


def _grounded_extractive_answer(
    question: str,
    sources: list[ChatSource],
    *,
    required_sources: int,
) -> tuple[list[ChatSource], list[str]] | None:
    """Choose directly relevant, verbatim evidence for either chat transport.

    Selecting a source sentence is not an entailment claim: the user-visible
    factual language remains byte-for-byte source text. The relevance score is
    deliberately used only to decide which *existing* sentence to display.
    Broad questions require one relevant sentence from every required source;
    a narrow question uses the strongest single sentence. For a narrative event
    question, the immediately following sentence can join that answer only
    when it has a shared event, object, or setting term rather than only a
    shared subject.
    """
    question_terms = _meaningful_terms(question)
    if not question_terms:
        return None

    if _asks_for_publication_metadata(question):
        for source in sources:
            for sentence in _sentences(source.text):
                if _is_publication_evidence(question, source.content_type, sentence):
                    return [source], [f"{sentence} [{source.source_id}]"]
        return None

    candidates: list[tuple[float, int, float, int, ChatSource, str]] = []
    broad_question = required_sources > 1
    for source_rank, source in enumerate(sources):
        best: tuple[float, int, float, int, ChatSource, str] | None = None
        for sentence_rank, sentence in enumerate(_sentences(source.text)):
            sentence_terms = _meaningful_terms(sentence)
            overlap = len(question_terms & sentence_terms)
            if overlap == 0:
                continue
            coverage = overlap / len(question_terms)
            event_primary_match = _is_event_question(question) and overlap >= 2
            if not broad_question and coverage < 0.5 and not event_primary_match:
                continue
            candidate = (
                coverage,
                overlap,
                source.score,
                -(source_rank * 1000 + sentence_rank),
                source,
                sentence,
            )
            if best is None or candidate[:4] > best[:4]:
                best = candidate
        if best is not None:
            candidates.append(best)

    if len(candidates) < required_sources:
        return None

    candidates.sort(key=lambda candidate: candidate[:4], reverse=True)
    selected: list[tuple[float, int, float, int, ChatSource, str]] = []
    seen_sentence_text: set[str] = set()
    for candidate in candidates:
        sentence_key = " ".join(candidate[5].casefold().split())
        if sentence_key in seen_sentence_text:
            continue
        seen_sentence_text.add(sentence_key)
        selected.append(candidate)
        if len(selected) == required_sources:
            break
    if len(selected) < required_sources:
        return None
    selected_sources = [candidate[4] for candidate in selected]
    tokens = [f"{candidate[5]} [{candidate[4].source_id}]" for candidate in selected]
    if not broad_question:
        primary = selected[0]
        context_sentence = _event_context_sentence(
            question,
            source=primary[4],
            primary_sentence=primary[5],
        )
        if context_sentence is not None:
            tokens.append(f"{context_sentence} [{primary[4].source_id}]")
        else:
            outcome = _event_outcome_from_retrieved_sources(
                question,
                sources=sources,
                primary_source=primary[4],
                primary_sentence=primary[5],
            )
            if outcome is not None:
                outcome_source, outcome_sentence = outcome
                tokens.append(f"{outcome_sentence} [{outcome_source.source_id}]")
                if outcome_source.chunk_id not in {
                    source.chunk_id for source in selected_sources
                }:
                    selected_sources.append(outcome_source)
    return selected_sources, tokens


def _semantic_source_selection_answer(
    question: str,
    sources: list[ChatSource],
    *,
    required_sources: int,
    answer_capability: str,
    generator: Generator,
) -> tuple[list[ChatSource], list[str]] | None:
    """Use a trusted Codex selector to choose exact, already-retrieved text.

    A selector gets no authority to draft an answer. It returns only IDs from
    the candidate source sentences below; strict validation then maps those IDs
    back to byte-for-byte book text. Every unavailable, malformed, or unsafe
    result returns ``None`` so the deterministic selector remains the fallback.
    """

    if _asks_for_publication_metadata(question):
        return None
    selector = _trusted_semantic_selector(
        answer_capability=answer_capability,
        generator=generator,
    )
    if selector is None:
        return None

    candidates = _source_sentence_candidates(sources)
    if not candidates:
        return None
    try:
        raw_selection = selector.generate(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "You select existing source sentence IDs for a book assistant. "
                        "Never write an answer, summary, explanation, citation, or new "
                        "sentence. Return only the requested JSON object."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=_semantic_selector_prompt(
                        question,
                        candidates,
                        required_sources=required_sources,
                    ),
                ),
            ],
            response_format="json",
        )
        return _validated_semantic_selection(
            raw_selection,
            candidates,
            required_sources=required_sources,
        )
    except (GenerationError, ValueError, TypeError, json.JSONDecodeError) as error:
        logger.info(
            "Semantic source selector unavailable; using deterministic fallback: %s",
            error,
        )
        return None


def _trusted_semantic_selector(
    *, answer_capability: str, generator: Generator
) -> Generator | None:
    """Return a selector only for an explicit quality Codex configuration.

    Request overrides cannot silently enable semantic selection. This limits
    semantic evidence choice to an administrator-owned JSON configuration and
    keeps Docker Ollama on the deterministic extractive path.
    """

    if answer_capability != "quality":
        return None
    try:
        config = get_librarian_config()
    except LibrarianConfigError:
        return None
    configured_generation = config.generation
    selector = config.semantic_source_selector
    configured_generation_mode = getattr(
        configured_generation, "mode", configured_generation.provider
    )
    if not selector.enabled or configured_generation.answer_capability != "quality":
        return None
    if selector.model != configured_generation.model or generator.model != selector.model:
        return None
    if (
        selector.provider == "codex"
        and configured_generation_mode == "codex"
        and generator.provider == "codex"
    ):
        try:
            return create_generator("codex", model=selector.model)
        except (GenerationError, LibrarianConfigError, ValueError) as error:
            logger.info("Semantic source selector is not configured for use: %s", error)
            return None
    if (
        selector.provider == "docker_codex_broker"
        and configured_generation_mode == "docker_codex_broker"
        and generator.provider == "openai_compatible"
    ):
        # This transport is only available through the Compose-owned broker
        # image. It carries a user-authenticated Codex CLI session, never a
        # host credential mount, and uses the normal OpenAI-compatible adapter.
        return generator
    return None


def _source_sentence_candidates(
    sources: list[ChatSource],
) -> list[_SourceSentenceCandidate]:
    """Give the selector stable IDs for exact sentences in scoped evidence."""

    return [
        _SourceSentenceCandidate(
            sentence_id=f"{source.source_id}:{sentence_index}",
            source=source,
            sentence=sentence,
        )
        for source in sources
        for sentence_index, sentence in enumerate(_sentences(source.text), start=1)
    ]


def _semantic_selector_prompt(
    question: str,
    candidates: list[_SourceSentenceCandidate],
    *,
    required_sources: int,
) -> str:
    """Build the source-ID-only contract sent to the trusted selector."""

    candidate_payload = [
        {
            "sentence_id": candidate.sentence_id,
            "source_id": candidate.source.source_id,
            "book_id": candidate.source.book_id,
            "title": candidate.source.title,
            "authors": candidate.source.authors,
            "sentence": candidate.sentence,
        }
        for candidate in candidates
    ]
    return (
        "Select the exact source sentences needed to answer the question. "
        "A differently worded question may refer to the same event, but do not "
        "infer a cause, reverse a relationship, or turn a negation into a positive "
        "claim. Select enough sentences to answer every part directly.\n\n"
        "Return exactly this JSON schema and no other keys:\n"
        '{"sentence_ids":["S1:1"]}\n\n'
        f"At least {required_sources} distinct source IDs must be represented. "
        "Every sentence_id must come from the candidate list and may appear once.\n\n"
        f"Question:\n{question}\n\n"
        f"Candidate source sentences:\n{json.dumps(candidate_payload, ensure_ascii=False)}"
    )


def _validated_semantic_selection(
    raw_selection: str,
    candidates: list[_SourceSentenceCandidate],
    *,
    required_sources: int,
) -> tuple[list[ChatSource], list[str]] | None:
    """Validate source IDs before mapping them back to exact cited text."""

    payload = json.loads(raw_selection)
    if not isinstance(payload, dict) or set(payload) != {"sentence_ids"}:
        return None
    sentence_ids = payload["sentence_ids"]
    if (
        not isinstance(sentence_ids, list)
        or not sentence_ids
        or any(
            not isinstance(sentence_id, str) or not sentence_id
            for sentence_id in sentence_ids
        )
        or len(set(sentence_ids)) != len(sentence_ids)
    ):
        return None

    candidates_by_id = {candidate.sentence_id: candidate for candidate in candidates}
    if any(sentence_id not in candidates_by_id for sentence_id in sentence_ids):
        return None
    selected = [candidates_by_id[sentence_id] for sentence_id in sentence_ids]
    # A sentence repeated across chunks cannot inflate broad-question coverage.
    normalized_sentences = {" ".join(item.sentence.casefold().split()) for item in selected}
    if len(normalized_sentences) != len(selected):
        return None
    distinct_chunks = {item.source.chunk_id for item in selected}
    if len(distinct_chunks) < required_sources:
        return None

    selected_sources: list[ChatSource] = []
    seen_chunks: set[str] = set()
    for item in selected:
        if item.source.chunk_id not in seen_chunks:
            selected_sources.append(item.source)
            seen_chunks.add(item.source.chunk_id)
    tokens = [f"{item.sentence} [{item.source.source_id}]" for item in selected]
    return selected_sources, tokens


def _event_context_sentence(
    question: str,
    *,
    source: ChatSource,
    primary_sentence: str,
) -> str | None:
    """Return one directly relevant next sentence for a narrative event query.

    This deliberately keeps the context rule local and conservative. The next
    source sentence must share an event, object, or setting term with the
    question or selected event sentence. A repeated actor or grammatical
    subject alone is not enough: adjacency never turns unrelated prose into an
    answer claim.
    """
    if not _is_event_question(question):
        return None
    sentences = _sentences(source.text)
    try:
        primary_index = sentences.index(primary_sentence)
    except ValueError:
        return None
    if primary_index + 1 >= len(sentences):
        return None

    context_sentence = sentences[primary_index + 1]
    context_terms = _meaningful_terms(context_sentence)
    event_context_terms = (
        _meaningful_terms(question) | _meaningful_terms(primary_sentence)
    ) - _leading_subject_terms(primary_sentence)
    if context_terms & event_context_terms:
        return context_sentence
    return None


def _event_outcome_from_retrieved_sources(
    question: str,
    *,
    sources: list[ChatSource],
    primary_source: ChatSource,
    primary_sentence: str,
) -> tuple[ChatSource, str] | None:
    """Find a directly anchored follow-up event from another retrieved chunk.

    Retrieval may split a short sequence at a chunk boundary.  For a question
    explicitly asking what happened immediately after an action, include one
    other retrieved sentence only when it shares a concrete object or setting
    term with the question or primary event.  Actor-name overlap alone is not
    enough, so unrelated adjacent narration stays out of the answer.
    """

    if not _is_event_question(question) or not _EVENT_FOLLOWUP_MARKER.search(question):
        return None
    primary_terms = _meaningful_terms(primary_sentence)
    anchors = (_meaningful_terms(question) | primary_terms) - _leading_subject_terms(
        primary_sentence
    )
    if not anchors:
        return None
    for source in sources:
        if source.chunk_id == primary_source.chunk_id:
            continue
        for sentence in _sentences(source.text):
            sentence_terms = _meaningful_terms(sentence)
            if sentence_terms & anchors:
                return source, sentence
    return None


def _is_event_question(question: str) -> bool:
    normalized = " ".join(question.casefold().split())
    return normalized.startswith(_EVENT_QUESTION_PREFIXES) or bool(
        _EVENT_FOLLOWUP_MARKER.search(normalized)
    )


def _leading_subject_terms(sentence: str) -> set[str]:
    """Return the first clause's simple subject term for adjacency filtering.

    Event context is intentionally a narrow display aid, not semantic parsing.
    Treating the leading meaningful word as the subject handles both character
    names (``Mara opened …``) and simple noun phrases (``The garden …``) while
    keeping the rule conservative when a full grammatical analysis is absent.
    """
    words = _WORD.findall(sentence.casefold())
    for word in words:
        if word in _QUESTION_STOP_WORDS or len(word) <= 1:
            continue
        return {_term_stem(word)}
    return set()


def _meaningful_terms(value: str) -> set[str]:
    return {
        _term_stem(term)
        for term in _WORD.findall(value.casefold())
        if term not in _QUESTION_STOP_WORDS and len(term) > 1
    }


def _term_stem(term: str) -> str:
    """Normalize only common English inflections used in factual lookups."""
    if term in {"wake", "wakes", "woke", "waking"}:
        return "wake"
    if term in {"publisher", "published", "publishing", "publishes"}:
        return "publish"
    if term.endswith("ies") and len(term) > 4:
        return f"{term[:-3]}y"
    if term.endswith(("ches", "shes", "sses", "xes", "zes")) and len(term) > 4:
        return term[:-2]
    if term.endswith("ed") and len(term) > 4:
        return term[:-2]
    if term.endswith("s") and len(term) > 3:
        return term[:-1]
    return term


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for line in text.splitlines()
        for sentence in _SENTENCE_BOUNDARY.split(line.strip())
        if sentence.strip()
    ]
