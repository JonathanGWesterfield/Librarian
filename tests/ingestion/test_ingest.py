import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_storage.storage import SQLiteIngestionStore


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


if __name__ == "__main__":
    unittest.main()
