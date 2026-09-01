import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_storage.storage import SQLiteIngestionStore
from tests.ingestion.fixtures import SAMPLE_EPUB


class IngestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingestion_can_enqueue_summary_jobs_without_generating_summaries(self) -> None:
        """Verify ingestion can schedule summary work and still return quickly.
        The queue records provider/model/detail for a separate worker, while
        ingestion itself only parses and stores books/chunks.
        """
        result = run_ingestion(
            IngestionOptions(
                books_dir=self.books_dir,
                database_url=self.database_url,
                enqueue_summaries=True,
                summary_generation_provider="codex",
                summary_generation_model="codex",
                summary_detail="medium",
            )
        )

        with SQLiteIngestionStore(self.database_path) as store:
            jobs = store.list_summary_jobs(status="pending")
            summaries = store.get_book_summary(
                book_id=jobs[0].book_id,
                provider="codex",
                model="codex",
                detail="medium",
            )

        self.assertEqual(result.parsed, 1)
        self.assertEqual(result.summary_jobs_enqueued, 1)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].provider, "codex")
        self.assertEqual(jobs[0].model, "codex")
        self.assertEqual(jobs[0].detail, "medium")
        self.assertIsNone(summaries)

    def test_ingestion_does_not_enqueue_summary_jobs_for_skipped_books(self) -> None:
        """Verify unchanged books do not create duplicate summary work.
        A second ingestion pass should keep the durable queue stable unless a
        book is actually parsed and stored again.
        """
        first = run_ingestion(
            IngestionOptions(
                books_dir=self.books_dir,
                database_url=self.database_url,
                enqueue_summaries=True,
                summary_generation_provider="codex",
                summary_generation_model="codex",
            )
        )
        second = run_ingestion(
            IngestionOptions(
                books_dir=self.books_dir,
                database_url=self.database_url,
                enqueue_summaries=True,
                summary_generation_provider="codex",
                summary_generation_model="codex",
            )
        )

        with SQLiteIngestionStore(self.database_path) as store:
            jobs = store.list_summary_jobs(status="pending")

        self.assertEqual(first.summary_jobs_enqueued, 1)
        self.assertEqual(second.summary_jobs_enqueued, 0)
        self.assertEqual(second.skipped_unchanged, 1)
        self.assertEqual(len(jobs), 1)

    def test_ingestion_rejects_invalid_summary_detail_before_parsing(self) -> None:
        """Verify invalid queued-summary configuration fails clearly.
        This keeps typoed detail levels out of durable job records.
        """
        with self.assertRaisesRegex(ValueError, "summary_detail"):
            run_ingestion(
                IngestionOptions(
                    books_dir=self.books_dir,
                    database_url=self.database_url,
                    enqueue_summaries=True,
                    summary_detail="verbose",
                )
            )

    def test_ingestion_stores_a_body_chapter_with_an_incidental_marker_in_its_name(self) -> None:
        """A chapter named stock-market must remain available to normal search."""
        with TemporaryDirectory() as temp_dir:
            books_dir = Path(temp_dir) / "books"
            books_dir.mkdir()
            _write_stock_market_epub(books_dir / "stock-market.epub")

            result = run_ingestion(
                IngestionOptions(
                    books_dir=books_dir,
                    database_url=self.database_url,
                )
            )

        with SQLiteIngestionStore(self.database_path) as store:
            stored_chunk = next(
                chunk
                for chunk in store.list_chunks()
                if "The stock market opened after the bell." in chunk.text
            )

        self.assertEqual(result.parsed, 1)
        self.assertEqual(stored_chunk.content_type, "body")


def _write_stock_market_epub(destination: Path) -> None:
    """Create a valid fixture EPUB with a body chapter whose name contains ``toc``."""
    manifest_item = (
        '    <item id="stock-market" href="stock-market.xhtml" '
        'media-type="application/xhtml+xml"/>\n'
    )
    spine_item = '    <itemref idref="stock-market"/>\n'
    chapter = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE html>
<html xmlns=\"http://www.w3.org/1999/xhtml\"><body>
  <h1>Stock Market</h1>
  <p>The stock market opened after the bell.</p>
</body></html>
"""
    with ZipFile(SAMPLE_EPUB) as source, ZipFile(destination, "w") as target:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if entry.filename == "OEBPS/content.opf":
                content = content.replace(
                    b"  </manifest>",
                    manifest_item.encode() + b"  </manifest>",
                ).replace(
                    b"  </spine>",
                    spine_item.encode() + b"  </spine>",
                )
            target.writestr(entry, content)
        target.writestr("OEBPS/stock-market.xhtml", chapter.encode())


if __name__ == "__main__":
    unittest.main()
