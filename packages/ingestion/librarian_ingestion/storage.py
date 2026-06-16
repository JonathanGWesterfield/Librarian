from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from librarian_ingestion.config import sqlite_path_from_url


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
        self, *, provider: str, model: str
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

    def list_books(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[StoredBookRecord]:
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
        self, *, provider: str, model: str
    ) -> list[SearchEmbeddingRecord]:
        # Only compare vectors produced by the same provider/model. Different
        # embedding models do not share a meaningful vector space.
        rows = self._connection.execute(
            """
            SELECT chunk_embeddings.chunk_id, chunks.book_id, books.relative_path,
                   books.title, books.authors_json, books.publisher,
                   chunks.chunk_index, chunks.text, chunk_embeddings.provider,
                   chunk_embeddings.model, chunk_embeddings.dimensions,
                   chunk_embeddings.vector_json
            FROM chunk_embeddings
            JOIN chunks ON chunks.id = chunk_embeddings.chunk_id
            JOIN books ON books.id = chunks.book_id
            WHERE chunk_embeddings.provider = ?
              AND chunk_embeddings.model = ?
            ORDER BY books.relative_path ASC, chunks.chunk_index ASC
            """,
            (provider, model),
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
"""
