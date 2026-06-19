from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from librarian_chat.generation import ChatMessage, create_configured_generator
from librarian_config.config import resolve_database_url
from librarian_storage.storage import (
    BookTagRecord,
    StoredBookTagRecord,
    StoredSummaryBookRecord,
    create_ingestion_store,
)

TAG_TYPE_TOPIC = "topic"
TAG_SOURCE_LLM = "llm"


@dataclass(frozen=True)
class GenerateBookTagsOptions:
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
    max_tags: int = 12
    force_refresh: bool = False
    reset: bool = False


@dataclass(frozen=True)
class GeneratedBookTag:
    tag: str
    confidence: float | None
    rationale: str | None
    cached: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BookTagGenerationResult:
    book_id: str
    title: str | None
    authors: list[str]
    source_summary_provider: str
    source_summary_model: str
    source_summary_detail: str
    generation_provider: str
    generation_model: str
    deleted_tags: int
    generated_tags: int
    cached_tags: int
    tags: list[GeneratedBookTag]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["tags"] = [tag.to_dict() for tag in self.tags]
        return payload


def generate_book_tags(options: GenerateBookTagsOptions) -> BookTagGenerationResult:
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
    max_tags = max(1, min(options.max_tags, 50))

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
                "book summary not found for tag generation: "
                f"{book.id} ({source_summary_provider}/{source_summary_model}/"
                f"{source_summary_detail})"
            )

        existing_tags = _matching_generated_tags(
            store.list_book_tags(
                book_id=book.id,
                tag_type=TAG_TYPE_TOPIC,
                source=TAG_SOURCE_LLM,
            ),
            provider=generator.provider,
            model=generator.model,
        )
        if existing_tags and not options.force_refresh and not options.reset:
            return BookTagGenerationResult(
                book_id=book.id,
                title=book.title,
                authors=book.authors,
                source_summary_provider=source_summary_provider,
                source_summary_model=source_summary_model,
                source_summary_detail=source_summary_detail,
                generation_provider=generator.provider,
                generation_model=generator.model,
                deleted_tags=0,
                generated_tags=0,
                cached_tags=len(existing_tags),
                tags=[
                    GeneratedBookTag(
                        tag=tag.tag,
                        confidence=tag.confidence,
                        rationale=tag.rationale,
                        cached=True,
                    )
                    for tag in existing_tags
                ],
            )

        deleted_tags = 0
        if options.reset:
            deleted_tags = store.delete_book_tags(
                book_id=book.id,
                tag_type=TAG_TYPE_TOPIC,
                source=TAG_SOURCE_LLM,
            )

        generated_tags = _parse_tag_response(
            # Ollama supports a transport-level JSON response mode through the
            # shared generator boundary. Codex CLI does not currently expose an
            # equivalent structured-output flag here, so Codex responses are
            # still validated before anything is persisted.
            generator.generate(
                _tag_generation_messages(
                    book=book,
                    summary=summary.summary,
                    max_tags=max_tags,
                ),
                response_format="json",
            ),
            max_tags=max_tags,
        )
        records = [
            BookTagRecord(
                id=_tag_id(
                    book_id=book.id,
                    tag=tag.tag,
                    tag_type=TAG_TYPE_TOPIC,
                    source=TAG_SOURCE_LLM,
                    provider=generator.provider,
                    model=generator.model,
                ),
                book_id=book.id,
                tag=tag.tag,
                tag_type=TAG_TYPE_TOPIC,
                source=TAG_SOURCE_LLM,
                confidence=tag.confidence,
                provider=generator.provider,
                model=generator.model,
                rationale=tag.rationale,
            )
            for tag in generated_tags
        ]
        store.save_book_tags(records)

        return BookTagGenerationResult(
            book_id=book.id,
            title=book.title,
            authors=book.authors,
            source_summary_provider=source_summary_provider,
            source_summary_model=source_summary_model,
            source_summary_detail=source_summary_detail,
            generation_provider=generator.provider,
            generation_model=generator.model,
            deleted_tags=deleted_tags,
            generated_tags=len(generated_tags),
            cached_tags=0,
            tags=generated_tags,
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
        raise ValueError("no ingested book matched the requested tag filters")
    if len(matches) > 1:
        titles = ", ".join(
            (match.title or match.relative_path) for match in matches[:5]
        )
        raise ValueError(
            "tag generation requires one book, but filters matched "
            f"{len(matches)} books: {titles}"
        )
    return matches[0]


def _tag_generation_messages(
    *,
    book: StoredSummaryBookRecord,
    summary: str,
    max_tags: int,
) -> list[ChatMessage]:
    title = book.title or book.relative_path
    authors = ", ".join(book.authors) if book.authors else "Unknown author"
    return [
        ChatMessage(
            role="system",
            content=(
                "You generate concise topic tags for a local book library. "
                "Return only valid JSON. Do not include genre labels such as "
                "fantasy, science fiction, literary fiction, horror, romance, "
                "or nonfiction. Genre classification is handled separately."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Book: {title}\n"
                f"Authors: {authors}\n"
                f"Maximum tags: {max_tags}\n\n"
                "Create topic/theme/concept tags that would help a reader find "
                "this book by subject. Return this exact shape:\n"
                "{\n"
                '  "tags": [\n'
                '    {"tag": "short tag", "confidence": 0.0, '
                '"rationale": "brief reason"}\n'
                "  ]\n"
                "}\n\n"
                f"Book summary:\n{summary}"
            ),
        ),
    ]


def _parse_tag_response(response: str, *, max_tags: int) -> list[GeneratedBookTag]:
    payload = _parse_json_payload(response)
    raw_tags = payload.get("tags")
    if not isinstance(raw_tags, list):
        raise ValueError("tag generator response must include a tags array")

    tags: list[GeneratedBookTag] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, dict):
            continue
        tag = _clean_filter(raw_tag.get("tag"))
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(
            GeneratedBookTag(
                tag=tag,
                confidence=_normalize_confidence(raw_tag.get("confidence")),
                rationale=_clean_filter(raw_tag.get("rationale")),
                cached=False,
            )
        )
        if len(tags) >= max_tags:
            break

    if not tags:
        raise ValueError("tag generator response did not include any usable tags")
    return tags


def _parse_json_payload(response: str) -> dict[str, Any]:
    cleaned = response.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("tag generator response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("tag generator response must be a JSON object")
    return payload


def _matching_generated_tags(
    tags: list[StoredBookTagRecord], *, provider: str, model: str
) -> list[StoredBookTagRecord]:
    return [
        tag
        for tag in tags
        if tag.provider == provider and tag.model == model
    ]


def _tag_id(
    *,
    book_id: str,
    tag: str,
    tag_type: str,
    source: str,
    provider: str,
    model: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "book_id": book_id,
                "tag": tag.strip().casefold(),
                "tag_type": tag_type,
                "source": source,
                "provider": provider,
                "model": model,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"book-tag:{digest}"


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
