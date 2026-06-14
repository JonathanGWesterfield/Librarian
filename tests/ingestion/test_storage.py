import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.ingestion.fixtures import SAMPLE_EPUB, SAMPLE_EPUB_SHA256

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
            title, authors_json = connection.execute(
                "SELECT title, authors_json FROM books WHERE relative_path = ?",
                ("sample.epub",),
            ).fetchone()
            first_chunk = connection.execute(
                "SELECT text FROM chunks WHERE book_id = ? ORDER BY chunk_index LIMIT 1",
                (SAMPLE_EPUB_SHA256,),
            ).fetchone()[0]

        self.assertEqual(title, "The Clockwork Garden")
        self.assertIn("Test Author", authors_json)
        self.assertIn("The clockwork garden woke at dawn.", first_chunk)


if __name__ == "__main__":
    unittest.main()
