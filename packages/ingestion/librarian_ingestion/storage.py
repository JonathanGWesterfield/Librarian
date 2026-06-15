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
class IngestionSummary:
    total_books: int
    total_chunks: int
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

    def count_books(self) -> int:
        ...

    def count_chunks(self) -> int:
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

    def count_books(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM books").fetchone()[0]

    def count_chunks(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

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
"""
