from __future__ import annotations

from dataclasses import asdict, dataclass

from librarian_chat.generation import ChatMessage, create_configured_generator
from librarian_config.config import resolve_database_url
from librarian_search.search import SearchOptions, SearchResult, search_chunks
from librarian_storage.storage import (
    StoredBookGenreRecord,
    StoredBookTagRecord,
    create_ingestion_store,
)


@dataclass(frozen=True)
class RecommendationOptions:
    query: str
    database_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    ollama_base_url: str | None = None
    limit: int = 5
    retrieval_limit: int = 40
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    genre: str | None = None
    tag: str | None = None


@dataclass(frozen=True)
class RecommendationEvidence:
    source_id: str
    score: float
    chunk_id: str
    chunk_index: int
    text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BookRecommendation:
    rank: int
    score: float
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    publisher: str | None
    tags: list[str]
    genres: list[str]
    evidence: list[RecommendationEvidence]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence"] = [evidence.to_dict() for evidence in self.evidence]
        return payload


@dataclass(frozen=True)
class RecommendationResponse:
    query: str
    answer: str
    embedding_provider: str
    embedding_model: str
    generation_provider: str
    generation_model: str
    retrieval_limit: int
    candidate_count: int
    filters: dict[str, str]
    recommendations: list[BookRecommendation]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "answer": self.answer,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "generation_provider": self.generation_provider,
            "generation_model": self.generation_model,
            "retrieval_limit": self.retrieval_limit,
            "candidate_count": self.candidate_count,
            "filters": self.filters,
            "recommendations": [
                recommendation.to_dict()
                for recommendation in self.recommendations
            ],
        }


@dataclass(frozen=True)
class _BookCandidate:
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    publisher: str | None
    chunks: list[SearchResult]
    tags: list[str]
    genres: list[str]


def recommend_books(options: RecommendationOptions) -> RecommendationResponse:
    query = options.query.strip()
    if not query:
        raise ValueError("recommendation query must not be empty")

    retrieval_limit = max(1, options.retrieval_limit)
    limit = max(1, options.limit)
    search_response = search_chunks(
        SearchOptions(
            query=query,
            database_url=options.database_url,
            embedding_provider=options.embedding_provider,
            embedding_model=options.embedding_model,
            ollama_base_url=options.ollama_base_url,
            limit=retrieval_limit,
            book_id=options.book_id,
            book_title=options.book_title,
            author=options.author,
        )
    )
    filters = _recommendation_filters(options, search_response.filters)
    metadata = _load_metadata_by_book(
        resolve_database_url(options.database_url),
        {result.book_id for result in search_response.results},
    )
    candidates = _build_candidates(search_response.results, metadata)
    candidates = _filter_candidates(candidates, genre=options.genre, tag=options.tag)
    ranked = _rank_candidates(candidates, query=query, limit=limit)

    generator = create_configured_generator(
        provider=options.generation_provider,
        model=options.generation_model,
        ollama_base_url=options.ollama_base_url,
    )
    answer = _build_no_candidate_answer(query)
    if ranked:
        answer = generator.generate(_recommendation_messages(query, ranked))

    return RecommendationResponse(
        query=query,
        answer=answer,
        embedding_provider=search_response.embedding_provider,
        embedding_model=search_response.embedding_model,
        generation_provider=generator.provider,
        generation_model=generator.model,
        retrieval_limit=retrieval_limit,
        candidate_count=len(candidates),
        filters=filters,
        recommendations=ranked,
    )


def _load_metadata_by_book(
    database_url: str,
    book_ids: set[str],
) -> dict[str, dict[str, list[str]]]:
    metadata = {
        book_id: {"tags": [], "genres": []}
        for book_id in book_ids
    }
    if not book_ids:
        return metadata

    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        tags = store.list_book_tags()
        genres = store.list_book_genres()
    finally:
        store.close()

    for tag in tags:
        if tag.book_id in metadata:
            metadata[tag.book_id]["tags"].append(_format_tag(tag))
    for genre in genres:
        if genre.book_id in metadata:
            metadata[genre.book_id]["genres"].append(_format_genre(genre))
    return metadata


def _build_candidates(
    results: list[SearchResult],
    metadata: dict[str, dict[str, list[str]]],
) -> list[_BookCandidate]:
    grouped: dict[str, list[SearchResult]] = {}
    for result in results:
        grouped.setdefault(result.book_id, []).append(result)

    candidates: list[_BookCandidate] = []
    for book_id, chunks in grouped.items():
        first = chunks[0]
        book_metadata = metadata.get(book_id, {"tags": [], "genres": []})
        candidates.append(
            _BookCandidate(
                book_id=book_id,
                relative_path=first.relative_path,
                title=first.title,
                authors=first.authors,
                publisher=first.publisher,
                chunks=chunks,
                tags=book_metadata["tags"],
                genres=book_metadata["genres"],
            )
        )
    return candidates


def _filter_candidates(
    candidates: list[_BookCandidate],
    *,
    genre: str | None,
    tag: str | None,
) -> list[_BookCandidate]:
    genre_filter = _clean_filter(genre)
    tag_filter = _clean_filter(tag)
    filtered: list[_BookCandidate] = []
    for candidate in candidates:
        if genre_filter and not _contains_value(candidate.genres, genre_filter):
            continue
        if tag_filter and not _contains_value(candidate.tags, tag_filter):
            continue
        filtered.append(candidate)
    return filtered


def _rank_candidates(
    candidates: list[_BookCandidate],
    *,
    query: str,
    limit: int,
) -> list[BookRecommendation]:
    query_key = query.casefold()
    scored = [
        (_recommendation_score(candidate, query_key), candidate)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: item[0], reverse=True)

    recommendations: list[BookRecommendation] = []
    for rank, (score, candidate) in enumerate(scored[:limit], start=1):
        recommendations.append(
            BookRecommendation(
                rank=rank,
                score=score,
                book_id=candidate.book_id,
                relative_path=candidate.relative_path,
                title=candidate.title,
                authors=candidate.authors,
                publisher=candidate.publisher,
                tags=candidate.tags,
                genres=candidate.genres,
                evidence=[
                    RecommendationEvidence(
                        source_id=f"R{rank}.{index}",
                        score=chunk.score,
                        chunk_id=chunk.chunk_id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                    )
                    for index, chunk in enumerate(candidate.chunks[:3], start=1)
                ],
            )
        )
    return recommendations


def _recommendation_score(candidate: _BookCandidate, query_key: str) -> float:
    chunk_scores = [chunk.score for chunk in candidate.chunks]
    top_chunk = max(chunk_scores) if chunk_scores else 0.0
    average_chunk = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0
    metadata_text = " ".join(
        [
            candidate.title or "",
            " ".join(candidate.authors),
            " ".join(candidate.tags),
            " ".join(candidate.genres),
        ]
    ).casefold()
    metadata_boost = 0.0
    for term in _query_terms(query_key):
        if term in metadata_text:
            metadata_boost += 0.04
    return round(top_chunk + (0.15 * average_chunk) + min(metadata_boost, 0.2), 6)


def _recommendation_messages(
    query: str,
    recommendations: list[BookRecommendation],
) -> list[ChatMessage]:
    book_cards = "\n\n".join(_format_book_card(item) for item in recommendations)
    return [
        ChatMessage(
            role="system",
            content=(
                "You recommend books from a local personal library. Use only "
                "the provided candidate books and evidence. Prefer concise, "
                "practical recommendations. Mention why each book fits and cite "
                "evidence IDs like [R1.1] when using retrieved text."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Reader request:\n{query}\n\n"
                f"Candidate books:\n{book_cards}\n\n"
                "Recommend the strongest fits. If the candidates are weak, say "
                "so plainly and explain what metadata or summaries are missing."
            ),
        ),
    ]


def _format_book_card(recommendation: BookRecommendation) -> str:
    title = recommendation.title or recommendation.relative_path
    authors = ", ".join(recommendation.authors) if recommendation.authors else "Unknown"
    tags = ", ".join(recommendation.tags) or "none"
    genres = ", ".join(recommendation.genres) or "none"
    evidence = "\n".join(
        f"[{item.source_id}] score={item.score:.4f} chunk={item.chunk_index}: {item.text}"
        for item in recommendation.evidence
    )
    return "\n".join(
        [
            f"Rank {recommendation.rank}: {title} by {authors}",
            f"Score: {recommendation.score:.4f}",
            f"Genres: {genres}",
            f"Tags: {tags}",
            "Evidence:",
            evidence,
        ]
    )


def _build_no_candidate_answer(query: str) -> str:
    return (
        "No recommendation candidates matched the current library data for "
        f"'{query}'. Try ingesting embeddings, generating tags/genres, or "
        "loosening filters."
    )


def _recommendation_filters(
    options: RecommendationOptions,
    search_filters: dict[str, str],
) -> dict[str, str]:
    filters = dict(search_filters)
    for key, value in {
        "genre": options.genre,
        "tag": options.tag,
    }.items():
        cleaned = _clean_filter(value)
        if cleaned:
            filters[key] = cleaned
    return filters


def _format_tag(tag: StoredBookTagRecord) -> str:
    return tag.tag


def _format_genre(genre: StoredBookGenreRecord) -> str:
    if genre.genre_role == "primary":
        return genre.genre
    return f"{genre.genre} ({genre.genre_role})"


def _contains_value(values: list[str], expected: str) -> bool:
    expected_key = expected.casefold()
    return any(expected_key in value.casefold() for value in values)


def _query_terms(query_key: str) -> list[str]:
    return [
        term
        for term in query_key.replace("-", " ").split()
        if len(term) >= 4
    ]


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
