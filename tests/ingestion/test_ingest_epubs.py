import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
