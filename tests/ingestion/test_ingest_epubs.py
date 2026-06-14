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
    def test_script_stores_sample_epub_and_skips_unchanged_second_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "librarian.db"
            database_url = f"sqlite:///{database_path}"
            books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"

            with redirect_stdout(StringIO()):
                first_exit = main(
                    [
                        "--books-dir",
                        str(books_dir),
                        "--database-url",
                        database_url,
                    ]
                )
                second_exit = main(
                    [
                        "--books-dir",
                        str(books_dir),
                        "--database-url",
                        database_url,
                    ]
                )

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)

            with sqlite3.connect(database_path) as connection:
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
