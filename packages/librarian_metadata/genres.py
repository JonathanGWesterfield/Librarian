from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from librarian_chat.generation import ChatMessage, create_configured_generator
from librarian_config.config import resolve_database_url
from librarian_storage.storage import (
    BookGenreRecord,
    StoredBookGenreRecord,
    StoredSummaryBookRecord,
    create_ingestion_store,
)

GENRE_ROLE_PRIMARY = "primary"
GENRE_ROLE_SECONDARY = "secondary"
GENRE_SOURCE_LLM = "llm"


@dataclass(frozen=True)
class GenerateBookGenresOptions:
    database_url: str | None = None
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    source_summary_provider: str | None = None
    source_summary_model: str | None = None
    source_summary_detail: str = "medium"
    generation_provider: str | None = None
    generation_model: str | None = None
    ollama_base_url: str | None = None
    max_secondary_genres: int = 3
    force_refresh: bool = False
    reset: bool = False


@dataclass(frozen=True)
class ListBookGenresOptions:
    database_url: str | None = None
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    genre_role: str | None = None
    source: str | None = None
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class DeleteBookGenresOptions:
    database_url: str | None = None
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    genre_role: str | None = None
    source: str | None = GENRE_SOURCE_LLM


@dataclass(frozen=True)
class GeneratedBookGenre:
    genre: str
    genre_role: str
    confidence: float | None
    rationale: str | None
    cached: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BookGenreGenerationResult:
    book_id: str
    title: str | None
    authors: list[str]
    source_summary_provider: str
    source_summary_model: str
    source_summary_detail: str
    generation_provider: str
    generation_model: str
    deleted_genres: int
    generated_genres: int
    cached_genres: int
    genres: list[GeneratedBookGenre]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["genres"] = [genre.to_dict() for genre in self.genres]
        return payload


def generate_book_genres(
    options: GenerateBookGenresOptions,
) -> BookGenreGenerationResult:
    database_url = resolve_database_url(options.database_url)
    generator = create_configured_generator(
        provider=options.generation_provider,
        model=options.generation_model,
        ollama_base_url=options.ollama_base_url,
    )
    source_summary_provider = (
        options.source_summary_provider or generator.provider
    ).strip().casefold()
    source_summary_model = (options.source_summary_model or generator.model).strip()
    source_summary_detail = _normalize_detail(options.source_summary_detail)
    max_secondary_genres = max(0, min(options.max_secondary_genres, 10))

    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        book = _resolve_single_book(
            store,
            book_id=options.book_id,
            book_title=options.book_title,
            author=options.author,
        )
        summary = store.get_book_summary(
            book_id=book.id,
            provider=source_summary_provider,
            model=source_summary_model,
            detail=source_summary_detail,
        )
        if summary is None:
            raise ValueError(
                "book summary not found for genre generation: "
                f"{book.id} ({source_summary_provider}/{source_summary_model}/"
                f"{source_summary_detail})"
            )

        existing_genres = _matching_generated_genres(
            store.list_book_genres(book_id=book.id, source=GENRE_SOURCE_LLM),
            provider=generator.provider,
            model=generator.model,
        )
        if existing_genres and not options.force_refresh and not options.reset:
            return BookGenreGenerationResult(
                book_id=book.id,
                title=book.title,
                authors=book.authors,
                source_summary_provider=source_summary_provider,
                source_summary_model=source_summary_model,
                source_summary_detail=source_summary_detail,
                generation_provider=generator.provider,
                generation_model=generator.model,
                deleted_genres=0,
                generated_genres=0,
                cached_genres=len(existing_genres),
                genres=[
                    GeneratedBookGenre(
                        genre=genre.genre,
                        genre_role=genre.genre_role,
                        confidence=genre.confidence,
                        rationale=genre.rationale,
                        cached=True,
                    )
                    for genre in existing_genres
                ],
            )

        deleted_genres = 0
        if options.reset:
            deleted_genres = store.delete_book_genres(
                book_id=book.id,
                source=GENRE_SOURCE_LLM,
            )

        generated_genres = _parse_genre_response(
            # Ollama supports transport-level JSON mode through the shared
            # generator. Codex is prompted with a strict template and then
            # validated locally before anything is stored.
            generator.generate(
                _genre_generation_messages(
                    book=book,
                    summary=summary.summary,
                    max_secondary_genres=max_secondary_genres,
                ),
                response_format="json",
            ),
            max_secondary_genres=max_secondary_genres,
        )
        records = [
            BookGenreRecord(
                id=_genre_id(
                    book_id=book.id,
                    genre=genre.genre,
                    genre_role=genre.genre_role,
                    source=GENRE_SOURCE_LLM,
                    provider=generator.provider,
                    model=generator.model,
                ),
                book_id=book.id,
                genre=genre.genre,
                genre_role=genre.genre_role,
                source=GENRE_SOURCE_LLM,
                confidence=genre.confidence,
                provider=generator.provider,
                model=generator.model,
                rationale=genre.rationale,
            )
            for genre in generated_genres
        ]
        store.save_book_genres(records)

        return BookGenreGenerationResult(
            book_id=book.id,
            title=book.title,
            authors=book.authors,
            source_summary_provider=source_summary_provider,
            source_summary_model=source_summary_model,
            source_summary_detail=source_summary_detail,
            generation_provider=generator.provider,
            generation_model=generator.model,
            deleted_genres=deleted_genres,
            generated_genres=len(generated_genres),
            cached_genres=0,
            genres=generated_genres,
        )
    finally:
        store.close()


def list_book_genres(options: ListBookGenresOptions) -> list[StoredBookGenreRecord]:
    database_url = resolve_database_url(options.database_url)
    provider = _clean_filter(options.provider)
    model = _clean_filter(options.model)
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        book_id = _resolve_optional_book_id(
            store,
            book_id=options.book_id,
            book_title=options.book_title,
            author=options.author,
        )
        genres = store.list_book_genres(
            book_id=book_id,
            genre_role=options.genre_role,
            source=options.source,
        )
        return [
            genre
            for genre in genres
            if (provider is None or genre.provider == provider)
            and (model is None or genre.model == model)
        ]
    finally:
        store.close()


def delete_book_genres(options: DeleteBookGenresOptions) -> int:
    database_url = resolve_database_url(options.database_url)
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        book_id = _resolve_optional_book_id(
            store,
            book_id=options.book_id,
            book_title=options.book_title,
            author=options.author,
        )
        if book_id is None:
            raise ValueError("deleting book genres requires --book-id or --book-title")
        return store.delete_book_genres(
            book_id=book_id,
            genre_role=options.genre_role,
            source=options.source,
        )
    finally:
        store.close()


def _resolve_single_book(
    store,
    *,
    book_id: str | None,
    book_title: str | None,
    author: str | None,
) -> StoredSummaryBookRecord:
    if book_id:
        book = store.get_summary_book(book_id.strip())
        if book is None:
            raise ValueError(f"book not found: {book_id}")
        return book

    title_filter = _clean_filter(book_title)
    author_filter = _clean_filter(author)
    matches = []
    for book in store.list_summary_books(limit=1000):
        title_matches = (
            not title_filter
            or title_filter.casefold() in (book.title or book.relative_path).casefold()
        )
        author_matches = not author_filter or any(
            author_filter.casefold() in stored_author.casefold()
            for stored_author in book.authors
        )
        if title_matches and author_matches:
            matches.append(book)

    if not matches:
        raise ValueError("no ingested book matched the requested genre filters")
    if len(matches) > 1:
        titles = ", ".join(
            (match.title or match.relative_path) for match in matches[:5]
        )
        raise ValueError(
            "genre generation requires one book, but filters matched "
            f"{len(matches)} books: {titles}"
        )
    return matches[0]


def _resolve_optional_book_id(
    store,
    *,
    book_id: str | None,
    book_title: str | None,
    author: str | None,
) -> str | None:
    if book_id or book_title or author:
        return _resolve_single_book(
            store,
            book_id=book_id,
            book_title=book_title,
            author=author,
        ).id
    return None


def _genre_generation_messages(
    *,
    book: StoredSummaryBookRecord,
    summary: str,
    max_secondary_genres: int,
) -> list[ChatMessage]:
    title = book.title or book.relative_path
    authors = ", ".join(book.authors) if book.authors else "Unknown author"
    return [
        ChatMessage(
            role="system",
            content=(
                "You classify books by genre for a local library. Complete the "
                "user's JSON object template by replacing only the example "
                "values. Return the completed JSON object and nothing else. "
                "Genres should be broad bookstore/library genres, not themes, "
                "subjects, moods, tropes, or reader-facing topic tags."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Book: {title}\n"
                f"Authors: {authors}\n"
                f"Maximum secondary genres: {max_secondary_genres}\n\n"
                "Classify this book with exactly one primary genre and up to "
                "the requested number of secondary genres. Fill in this JSON "
                "object template:\n"
                "{\n"
                '  "primary_genre": {"genre": "<broad genre>", '
                '"confidence": <0.0 to 1.0>, "rationale": "<brief reason>"},\n'
                '  "secondary_genres": [\n'
                '    {"genre": "<broad genre>", "confidence": <0.0 to 1.0>, '
                '"rationale": "<brief reason>"}\n'
                "  ]\n"
                "}\n"
                "Return only the completed JSON object. Do not wrap it in "
                "Markdown.\n\n"
                f"Book summary:\n{summary}"
            ),
        ),
    ]


def _parse_genre_response(
    response: str, *, max_secondary_genres: int
) -> list[GeneratedBookGenre]:
    payload = _parse_json_payload(response)
    primary_payload = payload.get("primary_genre")
    if not isinstance(primary_payload, dict):
        raise ValueError("genre generator response must include a primary_genre object")

    primary_genre = _parse_one_genre(primary_payload, role=GENRE_ROLE_PRIMARY)
    if primary_genre is None:
        raise ValueError("genre generator response did not include a usable primary genre")

    genres = [primary_genre]
    seen = {primary_genre.genre.casefold()}
    raw_secondary = payload.get("secondary_genres", [])
    if raw_secondary is None:
        raw_secondary = []
    if not isinstance(raw_secondary, list):
        raise ValueError("genre generator secondary_genres must be an array")

    for raw_genre in raw_secondary:
        if not isinstance(raw_genre, dict):
            continue
        genre = _parse_one_genre(raw_genre, role=GENRE_ROLE_SECONDARY)
        if genre is None:
            continue
        key = genre.genre.casefold()
        if key in seen:
            continue
        seen.add(key)
        genres.append(genre)
        if len(genres) - 1 >= max_secondary_genres:
            break

    return genres


def _parse_one_genre(
    raw_genre: dict[str, object], *, role: str
) -> GeneratedBookGenre | None:
    genre = _clean_filter(raw_genre.get("genre"))
    if not genre:
        return None
    return GeneratedBookGenre(
        genre=genre,
        genre_role=role,
        confidence=_normalize_confidence(raw_genre.get("confidence")),
        rationale=_clean_filter(raw_genre.get("rationale")),
        cached=False,
    )


def _parse_json_payload(response: str) -> dict[str, Any]:
    cleaned = response.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("genre generator response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("genre generator response must be a JSON object")
    return payload


def _matching_generated_genres(
    genres: list[StoredBookGenreRecord], *, provider: str, model: str
) -> list[StoredBookGenreRecord]:
    return [
        genre
        for genre in genres
        if genre.provider == provider and genre.model == model
    ]


def _genre_id(
    *,
    book_id: str,
    genre: str,
    genre_role: str,
    source: str,
    provider: str,
    model: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "book_id": book_id,
                "genre": genre.strip().casefold(),
                "genre_role": genre_role,
                "source": source,
                "provider": provider,
                "model": model,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"book-genre:{digest}"


def _normalize_confidence(value: object) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(confidence, 1.0))


def _normalize_detail(detail: str) -> str:
    normalized = detail.strip().casefold()
    if normalized not in {"short", "medium", "detailed"}:
        raise ValueError(f"unsupported summary detail level: {detail}")
    return normalized


def _clean_filter(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None
