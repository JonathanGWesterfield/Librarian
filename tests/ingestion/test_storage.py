import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.ingestion.fixtures import SAMPLE_EPUB, SAMPLE_EPUB_SHA256, SAMPLE_PUBLISHER

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.chunk import chunk_text
from librarian_ingestion.config import (
    resolve_database_url,
    sqlite_path_from_url,
)
from librarian_ingestion.epub import parse_epub
from librarian_ingestion.storage import (
    BookRecord,
    ChunkRecord,
    SQLiteIngestionStore,
    build_book_identity_key,
    create_ingestion_store,
    utc_now,
)


class DatabaseConfigTests(unittest.TestCase):
    def test_resolve_database_url_uses_env_then_default(self) -> None:
        """Verify database configuration follows the same env-first pattern.
        This lets local development use the default SQLite file while tests and
        future deployments can point storage somewhere else.
        """
        self.assertEqual(
            resolve_database_url(env={"LIBRARIAN_DATABASE_URL": "sqlite:///tmp.db"}),
            "sqlite:///tmp.db",
        )
        self.assertEqual(resolve_database_url(env={}), "sqlite:///data/librarian.db")

    def test_sqlite_path_from_url_accepts_relative_and_absolute_paths(self) -> None:
        """Verify SQLite URL parsing supports common local paths.
        The CLI accepts database URLs, but the SQLite adapter needs filesystem
        paths, so this test protects that translation.
        """
        self.assertEqual(sqlite_path_from_url("sqlite:///data/test.db"), Path("data/test.db"))
        self.assertEqual(sqlite_path_from_url("sqlite:////tmp/test.db"), Path("/tmp/test.db"))

    def test_sqlite_path_from_url_rejects_non_sqlite_url(self) -> None:
        """Verify SQLite-specific parsing refuses other database schemes.
        This keeps adapter selection explicit instead of accidentally treating a
        Postgres URL like a broken file path.
        """
        with self.assertRaises(ValueError):
            sqlite_path_from_url("postgresql://localhost/librarian")

    def test_create_ingestion_store_rejects_unimplemented_postgres(self) -> None:
        """Verify the adapter factory recognizes Postgres but blocks it for now.
        This documents the planned extension point while preventing callers from
        believing Postgres persistence already exists.
        """
        with self.assertRaises(NotImplementedError):
            create_ingestion_store("postgresql://localhost/librarian")

    def test_book_identity_key_uses_title_author_and_publisher(self) -> None:
        """Verify duplicate detection normalizes stable book metadata.
        Different casing or spacing should not hide duplicate books, while a
        different publisher can represent a distinct edition/source.
        """
        original = build_book_identity_key(
            "The Clockwork Garden", ["Test Author"], "Fixture Press"
        )
        normalized = build_book_identity_key(
            " the   clockwork garden ", ["test author"], "fixture press"
        )
        different_publisher = build_book_identity_key(
            "The Clockwork Garden", ["Test Author"], "Other Press"
        )

        self.assertEqual(original, normalized)
        self.assertNotEqual(original, different_publisher)


class SQLiteIngestionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_book_with_chunks_persists_book_and_chunks(self) -> None:
        """Verify the SQLite adapter persists the core ingestion records.
        This stores a parsed fixture book and its chunks, then reads them back
        through both the adapter and raw SQL to protect the schema contract.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        chunks = chunk_text(parsed.text, target_size=120, overlap=20)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )
        chunk_records = [
            ChunkRecord(
                id=f"{SAMPLE_EPUB_SHA256}:{chunk.chunk_index}",
                book_id=SAMPLE_EPUB_SHA256,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                character_count=chunk.character_count,
                token_estimate=chunk.token_estimate,
            )
            for chunk in chunks
        ]

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, chunk_records)

            self.assertEqual(store.count_books(), 1)
            self.assertEqual(store.count_chunks(), len(chunks))
            stored = store.get_book_by_relative_path("sample.epub")

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.file_hash, SAMPLE_EPUB_SHA256)
        self.assertEqual(stored.status, "ingested")
        self.assertEqual(stored.chunk_count, len(chunks))

        with sqlite3.connect(self.database_path) as connection:
            title, authors_json, publisher = connection.execute(
                "SELECT title, authors_json, publisher FROM books WHERE relative_path = ?",
                ("sample.epub",),
            ).fetchone()
            first_chunk = connection.execute(
                "SELECT text FROM chunks WHERE book_id = ? ORDER BY chunk_index LIMIT 1",
                (SAMPLE_EPUB_SHA256,),
            ).fetchone()[0]

        self.assertEqual(title, "The Clockwork Garden")
        self.assertIn("Test Author", authors_json)
        self.assertEqual(publisher, SAMPLE_PUBLISHER)
        self.assertIn("The clockwork garden woke at dawn.", first_chunk)

    def test_summary_and_book_listing_support_read_clients(self) -> None:
        """Verify desktop/API clients can inspect stored ingestion state.
        The summary and listing helpers provide read models without requiring
        callers to know the SQLite schema.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])

            summary = store.get_summary()
            books = store.list_books()

        self.assertEqual(summary.total_books, 1)
        self.assertEqual(summary.status_counts["ingested"], 1)
        self.assertEqual(books[0].title, "The Clockwork Garden")
        self.assertEqual(books[0].authors, ["Test Author"])

    def test_get_book_by_identity_finds_existing_book_metadata(self) -> None:
        """Verify the adapter can find an already ingested book by metadata.
        This is the guardrail that prevents a different file hash of the same
        title, author, and publisher from being ingested as another full book.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])

            stored = store.get_book_by_identity(
                " the clockwork garden ", ["test author"], SAMPLE_PUBLISHER
            )
            different_publisher = store.get_book_by_identity(
                "The Clockwork Garden", ["Test Author"], "Other Press"
            )

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.relative_path, "sample.epub")
        self.assertIsNone(different_publisher)


if __name__ == "__main__":
    unittest.main()
