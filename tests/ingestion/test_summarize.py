import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_storage.storage import (
    BookRecord,
    ChunkRecord,
    SQLiteIngestionStore,
    SummaryJobRecord,
    utc_now,
)
from librarian_summarization.jobs import (
    ProcessSummaryJobsOptions,
    process_summary_jobs,
)
from librarian_summarization.summarize import (
    DeleteSummariesOptions,
    SummarizeBookOptions,
    delete_summaries,
    summarize_book,
)


class SummarizeBookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_book()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_summarize_book_uses_ordered_chunk_windows_and_caches_results(self) -> None:
        """Verify first-pass book summarization works without chapter metadata.
        Many EPUBs do not expose clean chapter titles, so the summarizer should
        fall back to ordered chunk windows and then reuse cached summaries.
        """
        first_generator = _FakeGenerator()
        progress_events = []
        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            return_value=first_generator,
        ):
            first = summarize_book(
                SummarizeBookOptions(
                    database_url=self.database_url,
                    book_title="Forward",
                    author="Isaac Asimov",
                    generation_provider="codex",
                    generation_model="codex",
                    chunks_per_section=2,
                    progress_callback=progress_events.append,
                )
            )

        self.assertEqual(first.title, "Forward the Foundation")
        self.assertEqual(first.chapter_summary_count, 3)
        self.assertEqual(first.generated_chapter_summaries, 3)
        self.assertEqual(first.cached_chapter_summaries, 0)
        self.assertEqual(first.chapter_summaries[0].chapter_title, "Chunks 0-1")
        self.assertIn("Generated summary 4", first.summary)
        self.assertEqual(progress_events[0].stage, "plan")
        self.assertIn("Selected 3 section", progress_events[0].message)
        self.assertEqual(
            [event.stage for event in progress_events if event.stage == "chapter"],
            ["chapter", "chapter", "chapter"],
        )
        self.assertEqual(progress_events[-1].stage, "book")

        second_generator = _FakeGenerator()
        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            return_value=second_generator,
        ):
            second = summarize_book(
                SummarizeBookOptions(
                    database_url=self.database_url,
                    book_title="Forward",
                    author="Isaac Asimov",
                    generation_provider="codex",
                    generation_model="codex",
                    chunks_per_section=2,
                )
            )

        self.assertEqual(second.generated_chapter_summaries, 0)
        self.assertEqual(second.cached_chapter_summaries, 3)
        self.assertEqual(second.summary, first.summary)
        self.assertEqual(second_generator.calls, [])

    def test_summarize_book_reset_deletes_and_rebuilds_matching_summaries(self) -> None:
        """Verify reset gives us a clean benchmark run for a provider/model.
        This is the hook needed to compare Ollama and Codex summary quality
        without preserving stale summary rows from a previous run.
        """
        generator = _FakeGenerator()
        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            return_value=generator,
        ):
            summarize_book(
                SummarizeBookOptions(
                    database_url=self.database_url,
                    book_title="Forward",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    chunks_per_section=3,
                )
            )

        rebuild_generator = _FakeGenerator()
        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            return_value=rebuild_generator,
        ):
            rebuilt = summarize_book(
                SummarizeBookOptions(
                    database_url=self.database_url,
                    book_title="Forward",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    chunks_per_section=3,
                    reset=True,
                )
            )

        self.assertEqual(rebuilt.deleted_summaries, 3)
        self.assertEqual(rebuilt.generated_chapter_summaries, 2)
        self.assertEqual(len(rebuild_generator.calls), 3)

    def test_delete_summaries_removes_matching_rows_without_summarizing(self) -> None:
        """Verify summary deletion is available as its own operation.
        A standalone delete hook lets development runs clear cached summaries
        before switching LLM providers or prompt styles.
        """
        generator = _FakeGenerator()
        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            return_value=generator,
        ):
            summarize_book(
                SummarizeBookOptions(
                    database_url=self.database_url,
                    book_title="Forward",
                    generation_provider="codex",
                    generation_model="codex",
                    chunks_per_section=5,
                )
            )

        result = delete_summaries(
            DeleteSummariesOptions(
                database_url=self.database_url,
                book_title="Forward",
                generation_provider="codex",
                generation_model="codex",
                detail="medium",
            )
        )

        self.assertEqual(result.deleted_summaries, 2)

    def test_process_summary_jobs_generates_summary_and_marks_job_completed(self) -> None:
        """Verify queued summary jobs can be processed outside ingestion.
        Ingestion should only enqueue work; the worker owns actually calling
        the summarizer and recording job completion.
        """
        self._seed_summary_job()
        generator = _FakeGenerator()

        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            return_value=generator,
        ):
            result = process_summary_jobs(
                ProcessSummaryJobsOptions(database_url=self.database_url, limit=1)
            )

        with SQLiteIngestionStore(self.database_path) as store:
            completed_jobs = store.list_summary_jobs(status="completed")
            stored_summary = store.get_book_summary(
                book_id="forward-foundation",
                provider="codex",
                model="codex",
                detail="medium",
            )

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(completed_jobs[0].attempts, 1)
        self.assertIsNone(completed_jobs[0].error_message)
        self.assertIsNotNone(stored_summary)
        self.assertEqual(len(generator.calls), 2)

    def test_process_summary_jobs_marks_failed_job_without_stopping_worker(self) -> None:
        """Verify worker failures are persisted as job state.
        A bad provider or generation failure should not crash the queue; it
        should leave a useful error for the UI or CLI.
        """
        self._seed_summary_job()

        with patch(
            "librarian_summarization.summarize.create_configured_generator",
            side_effect=RuntimeError("model unavailable"),
        ):
            result = process_summary_jobs(
                ProcessSummaryJobsOptions(database_url=self.database_url, limit=1)
            )

        with SQLiteIngestionStore(self.database_path) as store:
            failed_jobs = store.list_summary_jobs(status="failed")

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.completed, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(failed_jobs[0].attempts, 1)
        self.assertEqual(failed_jobs[0].error_message, "model unavailable")

    def _seed_book(self) -> None:
        book = BookRecord(
            id="forward-foundation",
            source_path="/books/forward.epub",
            relative_path="Forward the Foundation - Isaac Asimov.epub",
            file_hash="forward-foundation",
            size_bytes=100,
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            status="ingested",
            ingested_at=utc_now(),
        )
        chunks = [
            ChunkRecord(
                id=f"forward-foundation:{index}",
                book_id="forward-foundation",
                chunk_index=index,
                text=f"Chunk {index} about Hari Seldon and psychohistory.",
                character_count=46,
                token_estimate=9,
            )
            for index in range(5)
        ]
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, chunks)

    def _seed_summary_job(self) -> None:
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_summary_job(
                SummaryJobRecord(
                    id="summary-job-1",
                    book_id="forward-foundation",
                    provider="codex",
                    model="codex",
                    detail="medium",
                )
            )


class _FakeGenerator:
    provider = "codex"
    model = "codex"

    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    def generate(self, messages, *, response_format=None):
        self.calls.append(messages)
        return f"Generated summary {len(self.calls)}"


if __name__ == "__main__":
    unittest.main()
