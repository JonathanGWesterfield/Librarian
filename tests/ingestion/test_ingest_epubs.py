import json
import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from tests.ingestion.fixtures import SAMPLE_EPUB_SHA256

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ingest_epubs import main


class IngestEpubsScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_script_stores_sample_epub_and_skips_unchanged_second_run(self) -> None:
        """Verify the real CLI entry point performs an idempotent ingestion.
        The first run should create one book plus chunks, while the second run
        should recognize the unchanged file hash and avoid duplicating records.
        """
        with redirect_stdout(StringIO()):
            first_exit = main(
                [
                    "--books-dir",
                    str(self.books_dir),
                    "--database-url",
                    self.database_url,
                ]
            )
            second_exit = main(
                [
                    "--books-dir",
                    str(self.books_dir),
                    "--database-url",
                    self.database_url,
                ]
            )

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)

        with sqlite3.connect(self.database_path) as connection:
            book_count = connection.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            file_hash = connection.execute(
                "SELECT file_hash FROM books WHERE relative_path = ?",
                ("sample.epub",),
            ).fetchone()[0]

        self.assertEqual(book_count, 1)
        self.assertGreater(chunk_count, 0)
        self.assertEqual(file_hash, SAMPLE_EPUB_SHA256)

    def test_script_can_emit_json_for_desktop_or_automation_clients(self) -> None:
        """Verify the CLI has a machine-readable integration path.
        A future Electron or Tauri shell can call the script and parse JSON
        instead of scraping human-oriented terminal output.
        """
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--books-dir",
                    str(self.books_dir),
                    "--database-url",
                    self.database_url,
                    "--json",
                ]
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["found"], 1)
        self.assertEqual(payload["parsed"], 1)
        self.assertEqual(payload["total_books"], 1)
        self.assertEqual(payload["embedding_provider"], "noop")
        self.assertEqual(payload["total_embeddings"], 0)

    def test_script_can_run_embedding_path_with_noop_provider(self) -> None:
        """Verify the embedding path can be enabled without a real model.
        This gives us coverage for the CLI flags and pipeline wiring while
        keeping unit tests independent from Ollama.
        """
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--books-dir",
                    str(self.books_dir),
                    "--database-url",
                    self.database_url,
                    "--embed",
                    "--embedding-provider",
                    "noop",
                    "--json",
                ]
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["stored_chunks"], 1)
        self.assertEqual(payload["stored_embeddings"], 0)
        self.assertEqual(payload["embedding_provider"], "noop")

    def test_script_marks_different_hash_with_same_metadata_as_duplicate(self) -> None:
        """Verify the CLI blocks duplicate books beyond exact file hashes.
        A copied EPUB with extra bytes has a different hash, but matching title,
        author, and publisher should be stored as duplicate without chunks.
        """
        duplicate_path = Path(self.temp_dir.name) / "duplicate-source.epub"
        copyfile(self.books_dir / "sample.epub", duplicate_path)
        with duplicate_path.open("ab") as file:
            file.write(b"\n")

        duplicate_books_dir = Path(self.temp_dir.name) / "books"
        duplicate_books_dir.mkdir()
        copyfile(self.books_dir / "sample.epub", duplicate_books_dir / "a-sample.epub")
        copyfile(duplicate_path, duplicate_books_dir / "z-sample-copy.epub")

        with redirect_stdout(StringIO()):
            exit_code = main(
                [
                    "--books-dir",
                    str(duplicate_books_dir),
                    "--database-url",
                    self.database_url,
                ]
            )

        self.assertEqual(exit_code, 0)

        with sqlite3.connect(self.database_path) as connection:
            statuses = dict(
                connection.execute(
                    "SELECT relative_path, status FROM books ORDER BY relative_path"
                ).fetchall()
            )
            duplicate_chunk_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM chunks
                WHERE book_id = (
                    SELECT id FROM books WHERE relative_path = 'z-sample-copy.epub'
                )
                """
            ).fetchone()[0]

        self.assertEqual(statuses["a-sample.epub"], "ingested")
        self.assertEqual(statuses["z-sample-copy.epub"], "duplicate")
        self.assertEqual(duplicate_chunk_count, 0)

    def test_script_marks_exact_file_copy_as_duplicate(self) -> None:
        """Verify duplicate detection handles exact copies under new filenames.
        Exact copies have the same SHA-256 hash, so duplicate records need a
        path-scoped database ID to avoid colliding with the ingested source.
        """
        duplicate_books_dir = Path(self.temp_dir.name) / "books"
        duplicate_books_dir.mkdir()
        copyfile(self.books_dir / "sample.epub", duplicate_books_dir / "a-sample.epub")
        copyfile(self.books_dir / "sample.epub", duplicate_books_dir / "z-sample-copy.epub")

        with redirect_stdout(StringIO()):
            exit_code = main(
                [
                    "--books-dir",
                    str(duplicate_books_dir),
                    "--database-url",
                    self.database_url,
                ]
            )

        self.assertEqual(exit_code, 0)

        with sqlite3.connect(self.database_path) as connection:
            statuses = dict(
                connection.execute(
                    "SELECT relative_path, status FROM books ORDER BY relative_path"
                ).fetchall()
            )

        self.assertEqual(statuses["a-sample.epub"], "ingested")
        self.assertEqual(statuses["z-sample-copy.epub"], "duplicate")


if __name__ == "__main__":
    unittest.main()
