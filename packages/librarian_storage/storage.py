from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from librarian_config.config import sqlite_path_from_url


@dataclass(frozen=True)
class BookRecord:
    id: str
    source_path: str
    relative_path: str
    file_hash: str
    size_bytes: int
    title: Optional[str]
    authors: list[str]
    status: str
    publisher: Optional[str] = None
    error_message: Optional[str] = None
    discovered_at: str = field(default_factory=lambda: utc_now())
    ingested_at: Optional[str] = None


@dataclass(frozen=True)
class ChunkRecord:
    id: str
    book_id: str
    chunk_index: int
    text: str
    character_count: int
    token_estimate: int
    chapter_title: Optional[str] = None
    created_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class EmbeddingRecord:
    id: str
    chunk_id: str
    provider: str
    model: str
    vector: list[float]
    dimensions: int
    created_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class StoredChunkRecord:
    id: str
    book_id: str
    chunk_index: int
    text: str
    character_count: int
    token_estimate: int
    chapter_title: Optional[str]


@dataclass(frozen=True)
class StoredBookSnapshot:
    id: str
    relative_path: str
    file_hash: str
    status: str
    chunk_count: int


@dataclass(frozen=True)
class StoredBookRecord:
    id: str
    relative_path: str
    title: Optional[str]
    authors: list[str]
    publisher: Optional[str]
    status: str
    error_message: Optional[str]
    chunk_count: int


@dataclass(frozen=True)
class StoredSummaryBookRecord:
    id: str
    relative_path: str
    title: Optional[str]
    authors: list[str]
    publisher: Optional[str]
    chunk_count: int


@dataclass(frozen=True)
class SummaryChunkRecord:
    id: str
    book_id: str
    chunk_index: int
    chapter_title: Optional[str]
    text: str


@dataclass(frozen=True)
class ChapterSummaryRecord:
    id: str
    book_id: str
    chapter_key: str
    chapter_title: Optional[str]
    chunk_start_index: int
    chunk_end_index: int
    provider: str
    model: str
    detail: str
    source_hash: str
    summary: str
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class BookSummaryRecord:
    id: str
    book_id: str
    provider: str
    model: str
    detail: str
    source_hash: str
    summary: str
    chapter_summary_count: int
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class SummaryJobRecord:
    id: str
    book_id: str
    provider: str
    model: str
    detail: str
    status: str = "pending"
    attempts: int = 0
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class StoredSummaryJobRecord:
    id: str
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    provider: str
    model: str
    detail: str
    status: str
    attempts: int
    error_message: str | None
    current_stage: str | None
    current_step: int | None
    total_steps: int | None
    progress_message: str | None
    progress_updated_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MetadataJobRecord:
    id: str
    book_id: str
    job_type: str
    source_summary_provider: str
    source_summary_model: str
    source_summary_detail: str
    generation_provider: str
    generation_model: str
    status: str = "pending"
    attempts: int = 0
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class StoredMetadataJobRecord:
    id: str
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    job_type: str
    source_summary_provider: str
    source_summary_model: str
    source_summary_detail: str
    generation_provider: str
    generation_model: str
    status: str
    attempts: int
    error_message: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class BookTagRecord:
    id: str
    book_id: str
    tag: str
    tag_type: str
    source: str
    confidence: float | None = None
    provider: str | None = None
    model: str | None = None
    rationale: str | None = None
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class StoredBookTagRecord:
    id: str
    book_id: str
    tag: str
    tag_type: str
    source: str
    confidence: float | None
    provider: str | None
    model: str | None
    rationale: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class BookGenreRecord:
    id: str
    book_id: str
    genre: str
    genre_role: str
    source: str
    confidence: float | None = None
    provider: str | None = None
    model: str | None = None
    rationale: str | None = None
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())


@dataclass(frozen=True)
class StoredBookGenreRecord:
    id: str
    book_id: str
    genre: str
    genre_role: str
    source: str
    confidence: float | None
    provider: str | None
    model: str | None
    rationale: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StoredEmbeddingRecord:
    id: str
    chunk_id: str
    book_id: str
    relative_path: str
    chunk_index: int
    provider: str
    model: str
    dimensions: int
    vector_sample: list[float]
    text_preview: str


@dataclass(frozen=True)
class SearchEmbeddingRecord:
    chunk_id: str
    book_id: str
    relative_path: str
    title: Optional[str]
    authors: list[str]
    publisher: Optional[str]
    chunk_index: int
    text: str
    provider: str
    model: str
    dimensions: int
    vector: list[float]


@dataclass(frozen=True)
class EmbeddingModelSummary:
    provider: str
    model: str
    dimensions: int
    embedding_count: int


@dataclass(frozen=True)
class IngestionSummary:
    total_books: int
    total_chunks: int
    total_embeddings: int
    status_counts: dict[str, int]


@dataclass(frozen=True)
class IngestionStageStatus:
    status: str
    total_books: int
    completed_books: int
    pending_books: int
    running_books: int
    failed_books: int
    percent_complete: float
    details: dict[str, int] = field(default_factory=dict)
    active_jobs: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class IngestionPipelineStatus:
    total_books: int
    chunking: IngestionStageStatus
    summarizing: IngestionStageStatus
    tagging: IngestionStageStatus


class IngestionStore(Protocol):
    def initialize(self) -> None:
        ...

    def get_book_by_relative_path(
        self, relative_path: str
    ) -> StoredBookSnapshot | None:
        ...

    def get_book_by_identity(
        self, title: Optional[str], authors: list[str], publisher: Optional[str]
    ) -> StoredBookSnapshot | None:
        ...

    def save_book_with_chunks(
        self, book: BookRecord, chunks: list[ChunkRecord]
    ) -> None:
        ...

    def save_chunk_embeddings(self, embeddings: list[EmbeddingRecord]) -> None:
        ...

    def delete_chunk_embeddings(
        self, *, provider: str | None = None, model: str | None = None
    ) -> int:
        ...

    def list_chunks(self, *, limit: int = 500, offset: int = 0) -> list[StoredChunkRecord]:
        ...

    def list_embeddings(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredEmbeddingRecord]:
        ...

    def get_embedding_model_summaries(self) -> list[EmbeddingModelSummary]:
        ...

    def list_search_embeddings(
        self,
        *,
        provider: str,
        model: str,
        book_id: str | None = None,
        book_title: str | None = None,
        author: str | None = None,
    ) -> list[SearchEmbeddingRecord]:
        ...

    def count_books(self) -> int:
        ...

    def count_chunks(self) -> int:
        ...

    def count_embeddings(self) -> int:
        ...

    def get_summary(self) -> IngestionSummary:
        ...

    def get_ingestion_status(self) -> IngestionPipelineStatus:
        ...

    def list_books(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[StoredBookRecord]:
        ...

    def get_summary_book(self, book_id: str) -> StoredSummaryBookRecord | None:
        ...

    def list_summary_books(self, *, limit: int = 500) -> list[StoredSummaryBookRecord]:
        ...

    def list_book_summary_chunks(self, book_id: str) -> list[SummaryChunkRecord]:
        ...

    def get_chapter_summary(
        self,
        *,
        book_id: str,
        chapter_key: str,
        provider: str,
        model: str,
        detail: str,
    ) -> ChapterSummaryRecord | None:
        ...

    def save_chapter_summary(self, summary: ChapterSummaryRecord) -> None:
        ...

    def get_book_summary(
        self, *, book_id: str, provider: str, model: str, detail: str
    ) -> BookSummaryRecord | None:
        ...

    def save_book_summary(self, summary: BookSummaryRecord) -> None:
        ...

    def delete_summaries(
        self,
        *,
        book_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        detail: str | None = None,
    ) -> int:
        ...

    def save_summary_job(self, job: SummaryJobRecord) -> None:
        ...

    def list_summary_jobs(
        self,
        *,
        status: str | None = None,
        book_id: str | None = None,
        limit: int = 100,
    ) -> list[StoredSummaryJobRecord]:
        ...

    def update_summary_job(
        self,
        job_id: str,
        *,
        status: str,
        attempts: int | None = None,
        error_message: str | None = None,
    ) -> None:
        ...

    def update_summary_job_progress(
        self,
        job_id: str,
        *,
        stage: str,
        current_step: int,
        total_steps: int,
        message: str,
    ) -> None:
        ...

    def claim_summary_job(self, job_id: str, *, attempts: int) -> bool:
        ...

    def save_metadata_job(self, job: MetadataJobRecord) -> None:
        ...

    def list_metadata_jobs(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        book_id: str | None = None,
        limit: int = 100,
    ) -> list[StoredMetadataJobRecord]:
        ...

    def update_metadata_job(
        self,
        job_id: str,
        *,
        status: str,
        attempts: int | None = None,
        error_message: str | None = None,
    ) -> None:
        ...

    def claim_metadata_job(self, job_id: str, *, attempts: int) -> bool:
        ...

    def save_book_tags(self, tags: list[BookTagRecord]) -> None:
        ...

    def list_book_tags(
        self,
        *,
        book_id: str | None = None,
        tag_type: str | None = None,
        source: str | None = None,
    ) -> list[StoredBookTagRecord]:
        ...

    def delete_book_tags(
        self,
        *,
        book_id: str | None = None,
        tag_type: str | None = None,
        source: str | None = None,
    ) -> int:
        ...

    def save_book_genres(self, genres: list[BookGenreRecord]) -> None:
        ...

    def list_book_genres(
        self,
        *,
        book_id: str | None = None,
        genre_role: str | None = None,
        source: str | None = None,
    ) -> list[StoredBookGenreRecord]:
        ...

    def delete_book_genres(
        self,
        *,
        book_id: str | None = None,
        genre_role: str | None = None,
        source: str | None = None,
    ) -> int:
        ...

    def close(self) -> None:
        ...


class SQLiteIngestionStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        self._migrate_schema()
        self.connection.commit()

    def _migrate_schema(self) -> None:
        columns = {
            row[1]
            for row in self._connection.execute("PRAGMA table_info(books)").fetchall()
        }
        if "publisher" not in columns:
            self._connection.execute("ALTER TABLE books ADD COLUMN publisher TEXT")
        if "identity_key" not in columns:
            self._connection.execute("ALTER TABLE books ADD COLUMN identity_key TEXT")
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_books_identity_key ON books(identity_key)"
        )
        rows = self._connection.execute(
            """
            SELECT id, title, authors_json, publisher
            FROM books
            WHERE identity_key IS NULL
            """
        ).fetchall()
        for book_id, title, authors_json, publisher in rows:
            try:
                authors = json.loads(authors_json)
            except json.JSONDecodeError:
                authors = []
            identity_key = build_book_identity_key(title, authors, publisher)
            if identity_key:
                self._connection.execute(
                    "UPDATE books SET identity_key = ? WHERE id = ?",
                    (identity_key, book_id),
                )
        self._migrate_summary_jobs_schema()

    def _migrate_summary_jobs_schema(self) -> None:
        columns = {
            row[1]
            for row in self._connection.execute(
                "PRAGMA table_info(summary_jobs)"
            ).fetchall()
        }
        progress_columns = {
            "current_stage": "TEXT",
            "current_step": "INTEGER",
            "total_steps": "INTEGER",
            "progress_message": "TEXT",
            "progress_updated_at": "TEXT",
        }
        for column, column_type in progress_columns.items():
            if column not in columns:
                self._connection.execute(
                    f"ALTER TABLE summary_jobs ADD COLUMN {column} {column_type}"
                )

    def get_book_by_relative_path(
        self, relative_path: str
    ) -> StoredBookSnapshot | None:
        row = self._connection.execute(
            """
            SELECT books.id, books.relative_path, books.file_hash, books.status,
                   COUNT(chunks.id) AS chunk_count
            FROM books
            LEFT JOIN chunks ON chunks.book_id = books.id
            WHERE books.relative_path = ?
            GROUP BY books.id
            """,
            (relative_path,),
        ).fetchone()
        if row is None:
            return None
        return StoredBookSnapshot(
            id=row[0],
            relative_path=row[1],
            file_hash=row[2],
            status=row[3],
            chunk_count=row[4],
        )

    def get_book_by_identity(
        self, title: Optional[str], authors: list[str], publisher: Optional[str]
    ) -> StoredBookSnapshot | None:
        identity_key = build_book_identity_key(title, authors, publisher)
        if identity_key is None:
            return None

        row = self._connection.execute(
            """
            SELECT books.id, books.relative_path, books.file_hash, books.status,
                   COUNT(chunks.id) AS chunk_count
            FROM books
            LEFT JOIN chunks ON chunks.book_id = books.id
            WHERE books.identity_key = ?
              AND books.status = 'ingested'
            GROUP BY books.id
            ORDER BY books.ingested_at ASC
            LIMIT 1
            """,
            (identity_key,),
        ).fetchone()
        if row is None:
            return None
        return StoredBookSnapshot(
            id=row[0],
            relative_path=row[1],
            file_hash=row[2],
            status=row[3],
            chunk_count=row[4],
        )

    def save_book_with_chunks(
        self, book: BookRecord, chunks: list[ChunkRecord]
    ) -> None:
        existing = self.get_book_by_relative_path(book.relative_path)
        updated_at = utc_now()

        with self._connection:
            if existing and existing.id != book.id:
                self._connection.execute(
                    "DELETE FROM chunks WHERE book_id = ?", (existing.id,)
                )
                self._connection.execute(
                    "DELETE FROM chapter_summaries WHERE book_id = ?", (existing.id,)
                )
                self._connection.execute(
                    "DELETE FROM book_summaries WHERE book_id = ?", (existing.id,)
                )
                self._connection.execute(
                    "DELETE FROM summary_jobs WHERE book_id = ?", (existing.id,)
                )
                self._connection.execute(
                    "DELETE FROM metadata_jobs WHERE book_id = ?", (existing.id,)
                )
                self._connection.execute(
                    "DELETE FROM book_tags WHERE book_id = ?", (existing.id,)
                )
                self._connection.execute(
                    "DELETE FROM book_genres WHERE book_id = ?", (existing.id,)
                )

            self._connection.execute(
                """
                INSERT INTO books (
                    id, source_path, relative_path, file_hash, size_bytes, title,
                    authors_json, publisher, identity_key, status, error_message, discovered_at,
                    ingested_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    id = excluded.id,
                    source_path = excluded.source_path,
                    file_hash = excluded.file_hash,
                    size_bytes = excluded.size_bytes,
                    title = excluded.title,
                    authors_json = excluded.authors_json,
                    publisher = excluded.publisher,
                    identity_key = excluded.identity_key,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    ingested_at = excluded.ingested_at,
                    updated_at = excluded.updated_at
                """,
                (
                    book.id,
                    book.source_path,
                    book.relative_path,
                    book.file_hash,
                    book.size_bytes,
                    book.title,
                    json.dumps(book.authors),
                    book.publisher,
                    build_book_identity_key(book.title, book.authors, book.publisher),
                    book.status,
                    book.error_message,
                    book.discovered_at,
                    book.ingested_at,
                    updated_at,
                ),
            )
            self._connection.execute(
                "DELETE FROM chunks WHERE book_id = ?", (book.id,)
            )
            self._connection.executemany(
                """
                INSERT INTO chunks (
                    id, book_id, chunk_index, chapter_title, text,
                    character_count, token_estimate, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.book_id,
                        chunk.chunk_index,
                        chunk.chapter_title,
                        chunk.text,
                        chunk.character_count,
                        chunk.token_estimate,
                        chunk.created_at,
                    )
                    for chunk in chunks
                ],
            )

    def save_chunk_embeddings(self, embeddings: list[EmbeddingRecord]) -> None:
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO chunk_embeddings (
                    id, chunk_id, provider, model, dimensions, vector_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id, provider, model) DO UPDATE SET
                    id = excluded.id,
                    dimensions = excluded.dimensions,
                    vector_json = excluded.vector_json,
                    created_at = excluded.created_at
                """,
                [
                    (
                        embedding.id,
                        embedding.chunk_id,
                        embedding.provider,
                        embedding.model,
                        embedding.dimensions,
                        json.dumps(embedding.vector),
                        embedding.created_at,
                    )
                    for embedding in embeddings
                ],
            )

    def delete_chunk_embeddings(
        self, *, provider: str | None = None, model: str | None = None
    ) -> int:
        where: list[str] = []
        parameters: list[object] = []
        if provider:
            where.append("provider = ?")
            parameters.append(provider)
        if model:
            where.append("model = ?")
            parameters.append(model)

        statement = "DELETE FROM chunk_embeddings"
        if where:
            statement = f"{statement} WHERE {' AND '.join(where)}"

        with self._connection:
            cursor = self._connection.execute(statement, parameters)
        return cursor.rowcount

    def list_chunks(
        self, *, limit: int = 500, offset: int = 0
    ) -> list[StoredChunkRecord]:
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        rows = self._connection.execute(
            """
            SELECT id, book_id, chunk_index, text, character_count,
                   token_estimate, chapter_title
            FROM chunks
            ORDER BY book_id ASC, chunk_index ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [
            StoredChunkRecord(
                id=row[0],
                book_id=row[1],
                chunk_index=row[2],
                text=row[3],
                character_count=row[4],
                token_estimate=row[5],
                chapter_title=row[6],
            )
            for row in rows
        ]

    def list_embeddings(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredEmbeddingRecord]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        where: list[str] = []
        parameters: list[object] = []
        if provider:
            where.append("chunk_embeddings.provider = ?")
            parameters.append(provider)
        if model:
            where.append("chunk_embeddings.model = ?")
            parameters.append(model)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        rows = self._connection.execute(
            f"""
            SELECT chunk_embeddings.id, chunk_embeddings.chunk_id, chunks.book_id,
                   books.relative_path, chunks.chunk_index, chunk_embeddings.provider,
                   chunk_embeddings.model, chunk_embeddings.dimensions,
                   chunk_embeddings.vector_json, chunks.text
            FROM chunk_embeddings
            JOIN chunks ON chunks.id = chunk_embeddings.chunk_id
            JOIN books ON books.id = chunks.book_id
            {where_sql}
            ORDER BY books.relative_path ASC, chunks.chunk_index ASC,
                     chunk_embeddings.provider ASC, chunk_embeddings.model ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        ).fetchall()
        return [
            StoredEmbeddingRecord(
                id=row[0],
                chunk_id=row[1],
                book_id=row[2],
                relative_path=row[3],
                chunk_index=row[4],
                provider=row[5],
                model=row[6],
                dimensions=row[7],
                vector_sample=_decode_vector_sample(row[8]),
                text_preview=_preview_text(row[9]),
            )
            for row in rows
        ]

    def get_embedding_model_summaries(self) -> list[EmbeddingModelSummary]:
        rows = self._connection.execute(
            """
            SELECT provider, model, dimensions, COUNT(*) AS embedding_count
            FROM chunk_embeddings
            GROUP BY provider, model, dimensions
            ORDER BY provider ASC, model ASC, dimensions ASC
            """
        ).fetchall()
        return [
            EmbeddingModelSummary(
                provider=row[0],
                model=row[1],
                dimensions=row[2],
                embedding_count=row[3],
            )
            for row in rows
        ]

    def list_search_embeddings(
        self,
        *,
        provider: str,
        model: str,
        book_id: str | None = None,
        book_title: str | None = None,
        author: str | None = None,
    ) -> list[SearchEmbeddingRecord]:
        # Only compare vectors produced by the same provider/model. Different
        # embedding models do not share a meaningful vector space.
        where = [
            "chunk_embeddings.provider = ?",
            "chunk_embeddings.model = ?",
        ]
        parameters: list[object] = [provider, model]
        if book_id:
            where.append("books.id = ?")
            parameters.append(book_id)
        if book_title:
            where.append("LOWER(COALESCE(books.title, '')) LIKE ?")
            parameters.append(f"%{book_title.strip().casefold()}%")
        if author:
            where.append("LOWER(books.authors_json) LIKE ?")
            parameters.append(f"%{author.strip().casefold()}%")

        rows = self._connection.execute(
            f"""
            SELECT chunk_embeddings.chunk_id, chunks.book_id, books.relative_path,
                   books.title, books.authors_json, books.publisher,
                   chunks.chunk_index, chunks.text, chunk_embeddings.provider,
                   chunk_embeddings.model, chunk_embeddings.dimensions,
                   chunk_embeddings.vector_json
            FROM chunk_embeddings
            JOIN chunks ON chunks.id = chunk_embeddings.chunk_id
            JOIN books ON books.id = chunks.book_id
            WHERE {' AND '.join(where)}
            ORDER BY books.relative_path ASC, chunks.chunk_index ASC
            """,
            parameters,
        ).fetchall()
        return [
            SearchEmbeddingRecord(
                chunk_id=row[0],
                book_id=row[1],
                relative_path=row[2],
                title=row[3],
                authors=_decode_authors(row[4]),
                publisher=row[5],
                chunk_index=row[6],
                text=row[7],
                provider=row[8],
                model=row[9],
                dimensions=row[10],
                vector=_decode_vector(row[11]),
            )
            for row in rows
        ]

    def count_books(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM books").fetchone()[0]

    def count_chunks(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def count_embeddings(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM chunk_embeddings"
        ).fetchone()[0]

    def get_summary(self) -> IngestionSummary:
        status_counts = {
            status: count
            for status, count in self._connection.execute(
                "SELECT status, COUNT(*) FROM books GROUP BY status"
            ).fetchall()
        }
        return IngestionSummary(
            total_books=self.count_books(),
            total_chunks=self.count_chunks(),
            total_embeddings=self.count_embeddings(),
            status_counts=status_counts,
        )

    def get_ingestion_status(self) -> IngestionPipelineStatus:
        total_books = self.count_books()
        return IngestionPipelineStatus(
            total_books=total_books,
            chunking=self._get_chunking_status(total_books),
            summarizing=self._get_summarizing_status(),
            tagging=self._get_tagging_status(),
        )

    def _get_chunking_status(self, total_books: int) -> IngestionStageStatus:
        chunked_books = self._chunked_book_count()
        failed_books = self._connection.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'failed'"
        ).fetchone()[0]
        ingested_books = self._connection.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'ingested'"
        ).fetchone()[0]
        pending_books = max(0, total_books - chunked_books - failed_books)
        return _stage_status(
            total_books=total_books,
            completed_books=chunked_books,
            pending_books=pending_books,
            failed_books=failed_books,
            details={
                "ingested_books": ingested_books,
                "total_chunks": self.count_chunks(),
            },
        )

    def _get_summarizing_status(self) -> IngestionStageStatus:
        total_books = self._chunked_book_count()
        completed_books = self._distinct_count("book_summaries", "book_id")
        status_counts = self._summary_job_status_counts()
        pending_jobs = status_counts.get("pending", 0)
        running_books = status_counts.get("running", 0)
        failed_books = status_counts.get("failed", 0)
        unqueued_books = max(0, total_books - self._summary_known_book_count())
        return _stage_status(
            total_books=total_books,
            completed_books=completed_books,
            pending_books=pending_jobs + unqueued_books,
            running_books=running_books,
            failed_books=failed_books,
            details={
                "book_summaries": self._count_table_rows("book_summaries"),
                "chapter_summaries": self._count_table_rows("chapter_summaries"),
                "summary_jobs_pending": pending_jobs,
                "summary_jobs_running": running_books,
                "summary_jobs_completed": status_counts.get("completed", 0),
                "summary_jobs_failed": failed_books,
                "unqueued_books": unqueued_books,
            },
            active_jobs=self._running_summary_job_progress(),
        )

    def _get_tagging_status(self) -> IngestionStageStatus:
        total_books = self._chunked_book_count()
        books_with_tags = self._distinct_count("book_tags", "book_id")
        books_with_genres = self._distinct_count("book_genres", "book_id")
        status_counts = self._metadata_job_status_counts()
        pending_jobs = status_counts.get("pending", 0)
        running_books = status_counts.get("running", 0)
        failed_books = status_counts.get("failed", 0)
        completed_books = self._connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT book_id FROM book_tags
                UNION
                SELECT book_id FROM book_genres
            )
            """
        ).fetchone()[0]
        return _stage_status(
            total_books=total_books,
            completed_books=completed_books,
            pending_books=max(0, total_books - completed_books) + pending_jobs,
            running_books=running_books,
            failed_books=failed_books,
            details={
                "books_with_tags": books_with_tags,
                "books_with_genres": books_with_genres,
                "total_tags": self._count_table_rows("book_tags"),
                "total_genres": self._count_table_rows("book_genres"),
                "metadata_jobs_pending": pending_jobs,
                "metadata_jobs_running": running_books,
                "metadata_jobs_completed": status_counts.get("completed", 0),
                "metadata_jobs_failed": failed_books,
            },
            active_jobs=self._running_metadata_job_progress(),
        )

    def _chunked_book_count(self) -> int:
        return self._connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT books.id
                FROM books
                JOIN chunks ON chunks.book_id = books.id
                WHERE books.status = 'ingested'
                GROUP BY books.id
            )
            """
        ).fetchone()[0]

    def _summary_known_book_count(self) -> int:
        return self._connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT book_id FROM book_summaries
                UNION
                SELECT book_id FROM summary_jobs
            )
            """
        ).fetchone()[0]

    def _summary_job_status_counts(self) -> dict[str, int]:
        return {
            row[0]: row[1]
            for row in self._connection.execute(
                "SELECT status, COUNT(DISTINCT book_id) FROM summary_jobs GROUP BY status"
            ).fetchall()
        }

    def _metadata_job_status_counts(self) -> dict[str, int]:
        return {
            row[0]: row[1]
            for row in self._connection.execute(
                "SELECT status, COUNT(DISTINCT book_id) FROM metadata_jobs GROUP BY status"
            ).fetchall()
        }

    def _running_summary_job_progress(self) -> list[dict[str, object]]:
        running_jobs = self.list_summary_jobs(status="running", limit=25)
        return [
            {
                "job_id": job.id,
                "book_id": job.book_id,
                "relative_path": job.relative_path,
                "title": job.title,
                "authors": job.authors,
                "provider": job.provider,
                "model": job.model,
                "detail": job.detail,
                "attempts": job.attempts,
                "stage": job.current_stage,
                "current": job.current_step,
                "total": job.total_steps,
                "message": job.progress_message,
                "updated_at": job.progress_updated_at,
            }
            for job in running_jobs
        ]

    def _running_metadata_job_progress(self) -> list[dict[str, object]]:
        running_jobs = self.list_metadata_jobs(status="running", limit=25)
        return [
            {
                "job_id": job.id,
                "book_id": job.book_id,
                "relative_path": job.relative_path,
                "title": job.title,
                "authors": job.authors,
                "job_type": job.job_type,
                "source_summary_provider": job.source_summary_provider,
                "source_summary_model": job.source_summary_model,
                "source_summary_detail": job.source_summary_detail,
                "provider": job.generation_provider,
                "model": job.generation_model,
                "attempts": job.attempts,
                "stage": "metadata",
                "current": 0,
                "total": 1,
                "message": f"Generating {job.job_type} metadata.",
                "updated_at": job.updated_at,
            }
            for job in running_jobs
        ]

    def _distinct_count(self, table: str, column: str) -> int:
        return self._connection.execute(
            f"SELECT COUNT(DISTINCT {column}) FROM {table}"
        ).fetchone()[0]

    def _count_table_rows(self, table: str) -> int:
        return self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def list_books(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[StoredBookRecord]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        parameters: list[object] = []
        where = ""
        if status:
            where = "WHERE books.status = ?"
            parameters.append(status)

        rows = self._connection.execute(
            f"""
            SELECT books.id, books.relative_path, books.title, books.authors_json,
                   books.publisher, books.status, books.error_message,
                   COUNT(chunks.id) AS chunk_count
            FROM books
            LEFT JOIN chunks ON chunks.book_id = books.id
            {where}
            GROUP BY books.id
            ORDER BY COALESCE(books.title, books.relative_path) ASC
            LIMIT ? OFFSET ?
            """,
            (*parameters, limit, offset),
        ).fetchall()
        return [
            StoredBookRecord(
                id=row[0],
                relative_path=row[1],
                title=row[2],
                authors=_decode_authors(row[3]),
                publisher=row[4],
                status=row[5],
                error_message=row[6],
                chunk_count=row[7],
            )
            for row in rows
        ]

    def get_summary_book(self, book_id: str) -> StoredSummaryBookRecord | None:
        row = self._connection.execute(
            """
            SELECT books.id, books.relative_path, books.title, books.authors_json,
                   books.publisher, COUNT(chunks.id) AS chunk_count
            FROM books
            LEFT JOIN chunks ON chunks.book_id = books.id
            WHERE books.id = ?
            GROUP BY books.id
            """,
            (book_id,),
        ).fetchone()
        if row is None:
            return None
        return StoredSummaryBookRecord(
            id=row[0],
            relative_path=row[1],
            title=row[2],
            authors=_decode_authors(row[3]),
            publisher=row[4],
            chunk_count=row[5],
        )

    def list_summary_books(self, *, limit: int = 500) -> list[StoredSummaryBookRecord]:
        limit = max(1, min(limit, 1000))
        rows = self._connection.execute(
            """
            SELECT books.id, books.relative_path, books.title, books.authors_json,
                   books.publisher, COUNT(chunks.id) AS chunk_count
            FROM books
            LEFT JOIN chunks ON chunks.book_id = books.id
            WHERE books.status = 'ingested'
            GROUP BY books.id
            ORDER BY COALESCE(books.title, books.relative_path) ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            StoredSummaryBookRecord(
                id=row[0],
                relative_path=row[1],
                title=row[2],
                authors=_decode_authors(row[3]),
                publisher=row[4],
                chunk_count=row[5],
            )
            for row in rows
        ]

    def list_book_summary_chunks(self, book_id: str) -> list[SummaryChunkRecord]:
        rows = self._connection.execute(
            """
            SELECT id, book_id, chunk_index, chapter_title, text
            FROM chunks
            WHERE book_id = ?
            ORDER BY chunk_index ASC
            """,
            (book_id,),
        ).fetchall()
        return [
            SummaryChunkRecord(
                id=row[0],
                book_id=row[1],
                chunk_index=row[2],
                chapter_title=row[3],
                text=row[4],
            )
            for row in rows
        ]

    def get_chapter_summary(
        self,
        *,
        book_id: str,
        chapter_key: str,
        provider: str,
        model: str,
        detail: str,
    ) -> ChapterSummaryRecord | None:
        row = self._connection.execute(
            """
            SELECT id, book_id, chapter_key, chapter_title, chunk_start_index,
                   chunk_end_index, provider, model, detail, source_hash,
                   summary, created_at, updated_at
            FROM chapter_summaries
            WHERE book_id = ?
              AND chapter_key = ?
              AND provider = ?
              AND model = ?
              AND detail = ?
            """,
            (book_id, chapter_key, provider, model, detail),
        ).fetchone()
        if row is None:
            return None
        return ChapterSummaryRecord(
            id=row[0],
            book_id=row[1],
            chapter_key=row[2],
            chapter_title=row[3],
            chunk_start_index=row[4],
            chunk_end_index=row[5],
            provider=row[6],
            model=row[7],
            detail=row[8],
            source_hash=row[9],
            summary=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    def save_chapter_summary(self, summary: ChapterSummaryRecord) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO chapter_summaries (
                    id, book_id, chapter_key, chapter_title, chunk_start_index,
                    chunk_end_index, provider, model, detail, source_hash,
                    summary, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, chapter_key, provider, model, detail)
                DO UPDATE SET
                    id = excluded.id,
                    chapter_title = excluded.chapter_title,
                    chunk_start_index = excluded.chunk_start_index,
                    chunk_end_index = excluded.chunk_end_index,
                    source_hash = excluded.source_hash,
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (
                    summary.id,
                    summary.book_id,
                    summary.chapter_key,
                    summary.chapter_title,
                    summary.chunk_start_index,
                    summary.chunk_end_index,
                    summary.provider,
                    summary.model,
                    summary.detail,
                    summary.source_hash,
                    summary.summary,
                    summary.created_at,
                    summary.updated_at,
                ),
            )

    def get_book_summary(
        self, *, book_id: str, provider: str, model: str, detail: str
    ) -> BookSummaryRecord | None:
        row = self._connection.execute(
            """
            SELECT id, book_id, provider, model, detail, source_hash, summary,
                   chapter_summary_count, created_at, updated_at
            FROM book_summaries
            WHERE book_id = ?
              AND provider = ?
              AND model = ?
              AND detail = ?
            """,
            (book_id, provider, model, detail),
        ).fetchone()
        if row is None:
            return None
        return BookSummaryRecord(
            id=row[0],
            book_id=row[1],
            provider=row[2],
            model=row[3],
            detail=row[4],
            source_hash=row[5],
            summary=row[6],
            chapter_summary_count=row[7],
            created_at=row[8],
            updated_at=row[9],
        )

    def save_book_summary(self, summary: BookSummaryRecord) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO book_summaries (
                    id, book_id, provider, model, detail, source_hash, summary,
                    chapter_summary_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, provider, model, detail)
                DO UPDATE SET
                    id = excluded.id,
                    source_hash = excluded.source_hash,
                    summary = excluded.summary,
                    chapter_summary_count = excluded.chapter_summary_count,
                    updated_at = excluded.updated_at
                """,
                (
                    summary.id,
                    summary.book_id,
                    summary.provider,
                    summary.model,
                    summary.detail,
                    summary.source_hash,
                    summary.summary,
                    summary.chapter_summary_count,
                    summary.created_at,
                    summary.updated_at,
                ),
            )

    def delete_summaries(
        self,
        *,
        book_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        detail: str | None = None,
    ) -> int:
        where: list[str] = []
        parameters: list[object] = []
        if book_id:
            where.append("book_id = ?")
            parameters.append(book_id)
        if provider:
            where.append("provider = ?")
            parameters.append(provider)
        if model:
            where.append("model = ?")
            parameters.append(model)
        if detail:
            where.append("detail = ?")
            parameters.append(detail)
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""

        with self._connection:
            chapter_cursor = self._connection.execute(
                f"DELETE FROM chapter_summaries{where_sql}",
                parameters,
            )
            book_cursor = self._connection.execute(
                f"DELETE FROM book_summaries{where_sql}",
                parameters,
            )
        return chapter_cursor.rowcount + book_cursor.rowcount

    def save_summary_job(self, job: SummaryJobRecord) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO summary_jobs (
                    id, book_id, provider, model, detail, status, attempts,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, provider, model, detail)
                DO UPDATE SET
                    id = excluded.id,
                    status = excluded.status,
                    attempts = excluded.attempts,
                    error_message = excluded.error_message,
                    current_stage = NULL,
                    current_step = NULL,
                    total_steps = NULL,
                    progress_message = NULL,
                    progress_updated_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    job.id,
                    job.book_id,
                    job.provider.strip().casefold(),
                    job.model.strip(),
                    job.detail.strip().casefold(),
                    job.status.strip().casefold(),
                    job.attempts,
                    job.error_message,
                    job.created_at,
                    job.updated_at,
                ),
            )

    def list_summary_jobs(
        self,
        *,
        status: str | None = None,
        book_id: str | None = None,
        limit: int = 100,
    ) -> list[StoredSummaryJobRecord]:
        where: list[str] = []
        parameters: list[object] = []
        if status:
            where.append("summary_jobs.status = ?")
            parameters.append(status.strip().casefold())
        if book_id:
            where.append("summary_jobs.book_id = ?")
            parameters.append(book_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        parameters.append(max(1, limit))

        rows = self._connection.execute(
            f"""
            SELECT summary_jobs.id, summary_jobs.book_id, books.relative_path,
                   books.title, books.authors_json, summary_jobs.provider,
                   summary_jobs.model, summary_jobs.detail, summary_jobs.status,
                   summary_jobs.attempts, summary_jobs.error_message,
                   summary_jobs.current_stage, summary_jobs.current_step,
                   summary_jobs.total_steps, summary_jobs.progress_message,
                   summary_jobs.progress_updated_at, summary_jobs.created_at,
                   summary_jobs.updated_at
            FROM summary_jobs
            JOIN books ON books.id = summary_jobs.book_id
            {where_sql}
            ORDER BY summary_jobs.created_at ASC, summary_jobs.id ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            StoredSummaryJobRecord(
                id=row[0],
                book_id=row[1],
                relative_path=row[2],
                title=row[3],
                authors=_decode_authors(row[4]),
                provider=row[5],
                model=row[6],
                detail=row[7],
                status=row[8],
                attempts=row[9],
                error_message=row[10],
                current_stage=row[11],
                current_step=row[12],
                total_steps=row[13],
                progress_message=row[14],
                progress_updated_at=row[15],
                created_at=row[16],
                updated_at=row[17],
            )
            for row in rows
        ]

    def update_summary_job(
        self,
        job_id: str,
        *,
        status: str,
        attempts: int | None = None,
        error_message: str | None = None,
    ) -> None:
        updates = ["status = ?", "error_message = ?", "updated_at = ?"]
        parameters: list[object] = [
            status.strip().casefold(),
            error_message,
            utc_now(),
        ]
        if attempts is not None:
            updates.insert(1, "attempts = ?")
            parameters.insert(1, attempts)
        parameters.append(job_id)
        with self._connection:
            self._connection.execute(
                f"UPDATE summary_jobs SET {', '.join(updates)} WHERE id = ?",
                parameters,
            )

    def update_summary_job_progress(
        self,
        job_id: str,
        *,
        stage: str,
        current_step: int,
        total_steps: int,
        message: str,
    ) -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                """
                UPDATE summary_jobs
                SET current_stage = ?, current_step = ?, total_steps = ?,
                    progress_message = ?, progress_updated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    stage.strip().casefold(),
                    max(0, current_step),
                    max(0, total_steps),
                    message,
                    now,
                    now,
                    job_id,
                ),
            )

    def claim_summary_job(self, job_id: str, *, attempts: int) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE summary_jobs
                SET status = ?, attempts = ?, error_message = ?,
                    current_stage = ?, current_step = ?, total_steps = ?,
                    progress_message = ?, progress_updated_at = ?,
                    updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    "running",
                    attempts,
                    None,
                    "queued",
                    0,
                    0,
                    "Summary job claimed by worker.",
                    utc_now(),
                    utc_now(),
                    job_id,
                    "pending",
                ),
            )
        return cursor.rowcount == 1

    def save_metadata_job(self, job: MetadataJobRecord) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO metadata_jobs (
                    id, book_id, job_type, source_summary_provider,
                    source_summary_model, source_summary_detail,
                    generation_provider, generation_model, status, attempts,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    book_id, job_type, source_summary_provider,
                    source_summary_model, source_summary_detail,
                    generation_provider, generation_model
                )
                DO UPDATE SET
                    id = excluded.id,
                    status = excluded.status,
                    attempts = excluded.attempts,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                WHERE metadata_jobs.status != 'completed'
                """,
                (
                    job.id,
                    job.book_id,
                    job.job_type.strip().casefold(),
                    job.source_summary_provider.strip().casefold(),
                    job.source_summary_model.strip(),
                    job.source_summary_detail.strip().casefold(),
                    job.generation_provider.strip().casefold(),
                    job.generation_model.strip(),
                    job.status.strip().casefold(),
                    job.attempts,
                    job.error_message,
                    job.created_at,
                    job.updated_at,
                ),
            )

    def list_metadata_jobs(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        book_id: str | None = None,
        limit: int = 100,
    ) -> list[StoredMetadataJobRecord]:
        where: list[str] = []
        parameters: list[object] = []
        if status:
            where.append("metadata_jobs.status = ?")
            parameters.append(status.strip().casefold())
        if job_type:
            where.append("metadata_jobs.job_type = ?")
            parameters.append(job_type.strip().casefold())
        if book_id:
            where.append("metadata_jobs.book_id = ?")
            parameters.append(book_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        parameters.append(max(1, limit))

        rows = self._connection.execute(
            f"""
            SELECT metadata_jobs.id, metadata_jobs.book_id, books.relative_path,
                   books.title, books.authors_json, metadata_jobs.job_type,
                   metadata_jobs.source_summary_provider,
                   metadata_jobs.source_summary_model,
                   metadata_jobs.source_summary_detail,
                   metadata_jobs.generation_provider,
                   metadata_jobs.generation_model, metadata_jobs.status,
                   metadata_jobs.attempts, metadata_jobs.error_message,
                   metadata_jobs.created_at, metadata_jobs.updated_at
            FROM metadata_jobs
            JOIN books ON books.id = metadata_jobs.book_id
            {where_sql}
            ORDER BY metadata_jobs.created_at ASC, metadata_jobs.id ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            StoredMetadataJobRecord(
                id=row[0],
                book_id=row[1],
                relative_path=row[2],
                title=row[3],
                authors=_decode_authors(row[4]),
                job_type=row[5],
                source_summary_provider=row[6],
                source_summary_model=row[7],
                source_summary_detail=row[8],
                generation_provider=row[9],
                generation_model=row[10],
                status=row[11],
                attempts=row[12],
                error_message=row[13],
                created_at=row[14],
                updated_at=row[15],
            )
            for row in rows
        ]

    def update_metadata_job(
        self,
        job_id: str,
        *,
        status: str,
        attempts: int | None = None,
        error_message: str | None = None,
    ) -> None:
        updates = ["status = ?", "error_message = ?", "updated_at = ?"]
        parameters: list[object] = [
            status.strip().casefold(),
            error_message,
            utc_now(),
        ]
        if attempts is not None:
            updates.insert(1, "attempts = ?")
            parameters.insert(1, attempts)
        parameters.append(job_id)
        with self._connection:
            self._connection.execute(
                f"UPDATE metadata_jobs SET {', '.join(updates)} WHERE id = ?",
                parameters,
            )

    def claim_metadata_job(self, job_id: str, *, attempts: int) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE metadata_jobs
                SET status = ?, attempts = ?, error_message = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                ("running", attempts, None, utc_now(), job_id, "pending"),
            )
        return cursor.rowcount == 1

    def save_book_tags(self, tags: list[BookTagRecord]) -> None:
        if not tags:
            return

        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO book_tags (
                    id, book_id, tag, tag_key, tag_type, source, confidence,
                    provider, model, rationale, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, tag_type, tag_key, source, provider, model)
                DO UPDATE SET
                    id = excluded.id,
                    tag = excluded.tag,
                    confidence = excluded.confidence,
                    rationale = excluded.rationale,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        tag.id,
                        tag.book_id,
                        tag.tag.strip(),
                        _book_tag_key(tag.tag),
                        tag.tag_type.strip().casefold(),
                        tag.source.strip().casefold(),
                        tag.confidence,
                        _empty_if_none(tag.provider),
                        _empty_if_none(tag.model),
                        tag.rationale,
                        tag.created_at,
                        tag.updated_at,
                    )
                    for tag in tags
                ],
            )

    def list_book_tags(
        self,
        *,
        book_id: str | None = None,
        tag_type: str | None = None,
        source: str | None = None,
    ) -> list[StoredBookTagRecord]:
        where: list[str] = []
        parameters: list[object] = []
        if book_id:
            where.append("book_id = ?")
            parameters.append(book_id)
        if tag_type:
            where.append("tag_type = ?")
            parameters.append(tag_type.strip().casefold())
        if source:
            where.append("source = ?")
            parameters.append(source.strip().casefold())
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        rows = self._connection.execute(
            f"""
            SELECT id, book_id, tag, tag_type, source, confidence, provider,
                   model, rationale, created_at, updated_at
            FROM book_tags
            {where_sql}
            ORDER BY book_id ASC, tag_type ASC, tag_key ASC, source ASC,
                     provider ASC, model ASC
            """,
            parameters,
        ).fetchall()
        return [
            StoredBookTagRecord(
                id=row[0],
                book_id=row[1],
                tag=row[2],
                tag_type=row[3],
                source=row[4],
                confidence=row[5],
                provider=_none_if_empty(row[6]),
                model=_none_if_empty(row[7]),
                rationale=row[8],
                created_at=row[9],
                updated_at=row[10],
            )
            for row in rows
        ]

    def delete_book_tags(
        self,
        *,
        book_id: str | None = None,
        tag_type: str | None = None,
        source: str | None = None,
    ) -> int:
        where: list[str] = []
        parameters: list[object] = []
        if book_id:
            where.append("book_id = ?")
            parameters.append(book_id)
        if tag_type:
            where.append("tag_type = ?")
            parameters.append(tag_type.strip().casefold())
        if source:
            where.append("source = ?")
            parameters.append(source.strip().casefold())
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""

        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM book_tags{where_sql}", parameters
            )
        return cursor.rowcount

    def save_book_genres(self, genres: list[BookGenreRecord]) -> None:
        if not genres:
            return

        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO book_genres (
                    id, book_id, genre, genre_key, genre_role, source, confidence,
                    provider, model, rationale, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, genre_role, genre_key, source, provider, model)
                DO UPDATE SET
                    id = excluded.id,
                    genre = excluded.genre,
                    confidence = excluded.confidence,
                    rationale = excluded.rationale,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        genre.id,
                        genre.book_id,
                        genre.genre.strip(),
                        _book_genre_key(genre.genre),
                        genre.genre_role.strip().casefold(),
                        genre.source.strip().casefold(),
                        genre.confidence,
                        _empty_if_none(genre.provider),
                        _empty_if_none(genre.model),
                        genre.rationale,
                        genre.created_at,
                        genre.updated_at,
                    )
                    for genre in genres
                ],
            )

    def list_book_genres(
        self,
        *,
        book_id: str | None = None,
        genre_role: str | None = None,
        source: str | None = None,
    ) -> list[StoredBookGenreRecord]:
        where: list[str] = []
        parameters: list[object] = []
        if book_id:
            where.append("book_id = ?")
            parameters.append(book_id)
        if genre_role:
            where.append("genre_role = ?")
            parameters.append(genre_role.strip().casefold())
        if source:
            where.append("source = ?")
            parameters.append(source.strip().casefold())
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        rows = self._connection.execute(
            f"""
            SELECT id, book_id, genre, genre_role, source, confidence, provider,
                   model, rationale, created_at, updated_at
            FROM book_genres
            {where_sql}
            ORDER BY book_id ASC, genre_role ASC, genre_key ASC, source ASC,
                     provider ASC, model ASC
            """,
            parameters,
        ).fetchall()
        return [
            StoredBookGenreRecord(
                id=row[0],
                book_id=row[1],
                genre=row[2],
                genre_role=row[3],
                source=row[4],
                confidence=row[5],
                provider=_none_if_empty(row[6]),
                model=_none_if_empty(row[7]),
                rationale=row[8],
                created_at=row[9],
                updated_at=row[10],
            )
            for row in rows
        ]

    def delete_book_genres(
        self,
        *,
        book_id: str | None = None,
        genre_role: str | None = None,
        source: str | None = None,
    ) -> int:
        where: list[str] = []
        parameters: list[object] = []
        if book_id:
            where.append("book_id = ?")
            parameters.append(book_id)
        if genre_role:
            where.append("genre_role = ?")
            parameters.append(genre_role.strip().casefold())
        if source:
            where.append("source = ?")
            parameters.append(source.strip().casefold())
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""

        with self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM book_genres{where_sql}", parameters
            )
        return cursor.rowcount

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def _connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("store is not initialized")
        return self.connection

    def __enter__(self) -> SQLiteIngestionStore:
        self.initialize()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_book_identity_key(
    title: Optional[str], authors: list[str], publisher: Optional[str]
) -> str | None:
    normalized_title = normalize_metadata_value(title)
    normalized_authors = sorted(
        author
        for author in (normalize_metadata_value(author) for author in authors)
        if author
    )
    if not normalized_title or not normalized_authors:
        return None

    return json.dumps(
        {
            "title": normalized_title,
            "authors": normalized_authors,
            "publisher": normalize_metadata_value(publisher) or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def normalize_metadata_value(value: Optional[str]) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return normalized or None


def _book_tag_key(tag: str) -> str:
    normalized = normalize_metadata_value(tag)
    if not normalized:
        raise ValueError("book tag must not be empty")
    return normalized


def _book_genre_key(genre: str) -> str:
    normalized = normalize_metadata_value(genre)
    if not normalized:
        raise ValueError("book genre must not be empty")
    return normalized


def _empty_if_none(value: str | None) -> str:
    return (value or "").strip()


def _none_if_empty(value: str) -> str | None:
    return value or None


def _decode_authors(authors_json: str) -> list[str]:
    try:
        authors = json.loads(authors_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(authors, list):
        return []
    return [author for author in authors if isinstance(author, str)]


def _decode_vector_sample(vector_json: str, sample_size: int = 5) -> list[float]:
    return _decode_vector(vector_json)[:sample_size]


def _decode_vector(vector_json: str) -> list[float]:
    try:
        vector = json.loads(vector_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(vector, list):
        return []
    decoded: list[float] = []
    for value in vector:
        try:
            decoded.append(float(value))
        except (TypeError, ValueError):
            continue
    return decoded


def _preview_text(text: str, max_length: int = 140) -> str:
    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) <= max_length:
        return preview
    return f"{preview[:max_length - 3]}..."


def _stage_status(
    *,
    total_books: int,
    completed_books: int,
    pending_books: int,
    running_books: int = 0,
    failed_books: int = 0,
    details: dict[str, int] | None = None,
    active_jobs: list[dict[str, object]] | None = None,
) -> IngestionStageStatus:
    if total_books <= 0:
        status = "empty"
        percent_complete = 0.0
    else:
        percent_complete = round((completed_books / total_books) * 100, 2)
        if running_books:
            status = "running"
        elif failed_books and completed_books + failed_books >= total_books:
            status = "failed"
        elif completed_books >= total_books:
            status = "complete"
        elif completed_books == 0 and pending_books:
            status = "not_started"
        else:
            status = "in_progress"

    return IngestionStageStatus(
        status=status,
        total_books=total_books,
        completed_books=completed_books,
        pending_books=pending_books,
        running_books=running_books,
        failed_books=failed_books,
        percent_complete=percent_complete,
        details=details or {},
        active_jobs=active_jobs or [],
    )


def create_ingestion_store(database_url: str) -> IngestionStore:
    if database_url.startswith("sqlite:///"):
        return SQLiteIngestionStore(sqlite_path_from_url(database_url))
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        raise NotImplementedError("Postgres ingestion storage is not implemented yet")
    raise ValueError(f"unsupported ingestion database URL: {database_url}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    file_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    title TEXT,
    authors_json TEXT NOT NULL,
    publisher TEXT,
    identity_key TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    discovered_at TEXT NOT NULL,
    ingested_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_books_file_hash ON books(file_hash);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chapter_title TEXT,
    text TEXT NOT NULL,
    character_count INTEGER NOT NULL,
    token_estimate INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(book_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_book_id ON chunks(book_id);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(chunk_id, provider, model)
);

CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_chunk_id
ON chunk_embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_provider_model
ON chunk_embeddings(provider, model);

CREATE TABLE IF NOT EXISTS chapter_summaries (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_key TEXT NOT NULL,
    chapter_title TEXT,
    chunk_start_index INTEGER NOT NULL,
    chunk_end_index INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, chapter_key, provider, model, detail)
);

CREATE INDEX IF NOT EXISTS idx_chapter_summaries_book_provider_model
ON chapter_summaries(book_id, provider, model, detail);

CREATE TABLE IF NOT EXISTS book_summaries (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    chapter_summary_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, provider, model, detail)
);

CREATE INDEX IF NOT EXISTS idx_book_summaries_book_provider_model
ON book_summaries(book_id, provider, model, detail);

CREATE TABLE IF NOT EXISTS summary_jobs (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, provider, model, detail)
);

CREATE INDEX IF NOT EXISTS idx_summary_jobs_status_created
ON summary_jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_summary_jobs_book
ON summary_jobs(book_id);

CREATE TABLE IF NOT EXISTS metadata_jobs (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    source_summary_provider TEXT NOT NULL,
    source_summary_model TEXT NOT NULL,
    source_summary_detail TEXT NOT NULL,
    generation_provider TEXT NOT NULL,
    generation_model TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(
        book_id, job_type, source_summary_provider, source_summary_model,
        source_summary_detail, generation_provider, generation_model
    )
);

CREATE INDEX IF NOT EXISTS idx_metadata_jobs_status_created
ON metadata_jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_metadata_jobs_book_type
ON metadata_jobs(book_id, job_type);

CREATE TABLE IF NOT EXISTS book_tags (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    tag_key TEXT NOT NULL,
    tag_type TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    rationale TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, tag_type, tag_key, source, provider, model)
);

CREATE INDEX IF NOT EXISTS idx_book_tags_book_type
ON book_tags(book_id, tag_type);

CREATE INDEX IF NOT EXISTS idx_book_tags_type_key
ON book_tags(tag_type, tag_key);

CREATE TABLE IF NOT EXISTS book_genres (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    genre TEXT NOT NULL,
    genre_key TEXT NOT NULL,
    genre_role TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    rationale TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(book_id, genre_role, genre_key, source, provider, model)
);

CREATE INDEX IF NOT EXISTS idx_book_genres_book_role
ON book_genres(book_id, genre_role);

CREATE INDEX IF NOT EXISTS idx_book_genres_role_key
ON book_genres(genre_role, genre_key);
"""
