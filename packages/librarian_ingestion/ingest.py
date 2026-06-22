from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from librarian_ingestion.chunk import chunk_text
from librarian_config.config import (
    resolve_books_dir,
    resolve_database_url,
    resolve_embedding_model,
    resolve_embedding_provider,
    resolve_generation_model,
    resolve_generation_provider,
)
from librarian_ingestion.embeddings import create_configured_embedder
from librarian_ingestion.epub import parse_epub
from librarian_ingestion.scan import DiscoveredEpub, scan_epub_files
from librarian_storage.storage import (
    BookRecord,
    ChunkRecord,
    EmbeddingRecord,
    SummaryJobRecord,
    create_ingestion_store,
    utc_now,
)


@dataclass(frozen=True)
class IngestionOptions:
    books_dir: str | Path | None = None
    database_url: str | None = None
    force: bool = False
    list_epubs: bool = False
    embed_chunks: bool = False
    embedding_provider: str | None = None
    embedding_model: str | None = None
    ollama_base_url: str | None = None
    embedding_batch_size: int = 16
    enqueue_summaries: bool = False
    summary_generation_provider: str | None = None
    summary_generation_model: str | None = None
    summary_detail: str = "medium"


@dataclass(frozen=True)
class BookIngestionResult:
    relative_path: str
    file_hash: str
    status: str
    chunk_count: int = 0
    message: str | None = None


@dataclass(frozen=True)
class IngestionResult:
    books_dir: str
    database_url: str
    embedding_provider: str
    embedding_model: str
    found: int
    parsed: int = 0
    skipped_unchanged: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    stored_chunks: int = 0
    stored_embeddings: int = 0
    summary_jobs_enqueued: int = 0
    total_books: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0
    books: list[BookIngestionResult] = field(default_factory=list)
    discovered: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_ingestion(options: IngestionOptions | None = None) -> IngestionResult:
    options = options or IngestionOptions()
    books_dir = resolve_books_dir(options.books_dir)
    database_url = resolve_database_url(options.database_url)
    embedding_provider = resolve_embedding_provider(options.embedding_provider)
    embedding_model = resolve_embedding_model(options.embedding_model)
    summary_provider = resolve_generation_provider(options.summary_generation_provider)
    summary_model = (
        "codex"
        if summary_provider.strip().casefold() == "codex"
        and options.summary_generation_model is None
        else resolve_generation_model(options.summary_generation_model)
    )
    summary_detail = _normalize_summary_detail(options.summary_detail)
    discovered_epubs = scan_epub_files(books_dir)
    book_results: list[BookIngestionResult] = []

    parsed_count = 0
    skipped_count = 0
    duplicate_count = 0
    failed_count = 0
    chunk_count = 0
    embedding_count = 0
    summary_job_count = 0
    embedder = None
    if options.embed_chunks:
        embedder = create_configured_embedder(
            provider=options.embedding_provider,
            model=options.embedding_model,
            ollama_base_url=options.ollama_base_url,
        )

    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        for discovered in discovered_epubs:
            existing = store.get_book_by_relative_path(discovered.relative_path)
            if (
                existing
                and existing.file_hash == discovered.sha256
                and existing.status == "ingested"
                and not options.force
            ):
                skipped_count += 1
                book_results.append(
                    _book_result(discovered, "skipped_unchanged", existing.chunk_count)
                )
                continue

            try:
                parsed = parse_epub(discovered.path)
                duplicate = store.get_book_by_identity(
                    parsed.title, parsed.authors, parsed.publisher
                )
                if duplicate and duplicate.relative_path != discovered.relative_path and not options.force:
                    message = (
                        "Duplicate metadata matches already ingested book: "
                        f"{duplicate.relative_path}"
                    )
                    duplicate_book = _book_record(
                        discovered, parsed.title, parsed.authors, parsed.publisher,
                        "duplicate", message
                    )
                    store.save_book_with_chunks(duplicate_book, [])
                    duplicate_count += 1
                    book_results.append(
                        _book_result(discovered, "duplicate", message=message)
                    )
                    continue

                chunks = chunk_text(parsed.text)
                book = _book_record(
                    discovered,
                    parsed.title,
                    parsed.authors,
                    parsed.publisher,
                    "ingested",
                    ingested_at=utc_now(),
                )
                chunk_records = [
                    ChunkRecord(
                        id=f"{discovered.sha256}:{chunk.chunk_index}",
                        book_id=discovered.sha256,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        character_count=chunk.character_count,
                        token_estimate=chunk.token_estimate,
                    )
                    for chunk in chunks
                ]
                store.save_book_with_chunks(book, chunk_records)
                if embedder is not None:
                    embedding_records = _embed_chunks(
                        chunk_records,
                        provider=embedder.provider,
                        model=embedder.model,
                        batch_size=options.embedding_batch_size,
                        embed_texts=embedder.embed_texts,
                    )
                    store.save_chunk_embeddings(embedding_records)
                    embedding_count += len(embedding_records)
                if options.enqueue_summaries:
                    store.save_summary_job(
                        SummaryJobRecord(
                            id=_summary_job_id(
                                book_id=book.id,
                                provider=summary_provider,
                                model=summary_model,
                                detail=summary_detail,
                            ),
                            book_id=book.id,
                            provider=summary_provider,
                            model=summary_model,
                            detail=summary_detail,
                        )
                    )
                    summary_job_count += 1
                parsed_count += 1
                chunk_count += len(chunk_records)
                book_results.append(
                    _book_result(discovered, "ingested", len(chunk_records))
                )
            except Exception as error:
                message = str(error)
                failed_count += 1
                failed_book = _book_record(discovered, None, [], None, "failed", message)
                store.save_book_with_chunks(failed_book, [])
                book_results.append(_book_result(discovered, "failed", message=message))

        total_books = store.count_books()
        total_chunks = store.count_chunks()
        total_embeddings = store.count_embeddings()
    finally:
        store.close()

    discovered = [
        {
            "relative_path": epub.relative_path,
            "size_bytes": epub.size_bytes,
            "sha256": epub.sha256,
        }
        for epub in discovered_epubs
    ] if options.list_epubs else []

    return IngestionResult(
        books_dir=str(books_dir),
        database_url=database_url,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        found=len(discovered_epubs),
        parsed=parsed_count,
        skipped_unchanged=skipped_count,
        skipped_duplicates=duplicate_count,
        failed=failed_count,
        stored_chunks=chunk_count,
        stored_embeddings=embedding_count,
        summary_jobs_enqueued=summary_job_count,
        total_books=total_books,
        total_chunks=total_chunks,
        total_embeddings=total_embeddings,
        books=book_results,
        discovered=discovered,
    )


def _summary_job_id(*, book_id: str, provider: str, model: str, detail: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "book_id": book_id,
                "provider": provider.strip().casefold(),
                "model": model.strip(),
                "detail": detail.strip().casefold(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"summary-job:{digest}"


def _normalize_summary_detail(detail: str) -> str:
    normalized = detail.strip().casefold()
    if normalized not in {"short", "medium", "detailed"}:
        raise ValueError("summary_detail must be one of: short, medium, detailed")
    return normalized


def _embed_chunks(
    chunks: list[ChunkRecord],
    *,
    provider: str,
    model: str,
    batch_size: int,
    embed_texts,
) -> list[EmbeddingRecord]:
    if not chunks:
        return []

    records: list[EmbeddingRecord] = []
    safe_batch_size = max(1, batch_size)
    for start in range(0, len(chunks), safe_batch_size):
        batch = chunks[start:start + safe_batch_size]
        vectors = embed_texts([chunk.text for chunk in batch])
        if not vectors:
            continue
        if len(vectors) != len(batch):
            raise ValueError("embedder returned a different number of vectors")
        for chunk, vector in zip(batch, vectors):
            records.append(
                EmbeddingRecord(
                    id=f"{chunk.id}:{provider}:{model}",
                    chunk_id=chunk.id,
                    provider=provider,
                    model=model,
                    vector=vector,
                    dimensions=len(vector),
                )
            )
    return records


def _book_record(
    discovered: DiscoveredEpub,
    title: str | None,
    authors: list[str],
    publisher: str | None,
    status: str,
    error_message: str | None = None,
    ingested_at: str | None = None,
) -> BookRecord:
    book_id = discovered.sha256
    if status != "ingested":
        book_id = f"{discovered.sha256}:{discovered.relative_path}"

    return BookRecord(
        id=book_id,
        source_path=str(discovered.path),
        relative_path=discovered.relative_path,
        file_hash=discovered.sha256,
        size_bytes=discovered.size_bytes,
        title=title,
        authors=authors,
        publisher=publisher,
        status=status,
        error_message=error_message,
        ingested_at=ingested_at,
    )


def _book_result(
    discovered: DiscoveredEpub,
    status: str,
    chunk_count: int = 0,
    message: str | None = None,
) -> BookIngestionResult:
    return BookIngestionResult(
        relative_path=discovered.relative_path,
        file_hash=discovered.sha256,
        status=status,
        chunk_count=chunk_count,
        message=message,
    )
