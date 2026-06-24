from __future__ import annotations

from dataclasses import dataclass
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_metadata.jobs import (
    EnqueueMetadataJobsOptions,
    MetadataJobWorkerOptions,
    ProcessMetadataJobsOptions,
    enqueue_metadata_jobs,
    process_metadata_jobs,
    run_metadata_job_worker,
)
from librarian_storage.storage import (
    BookRecord,
    BookSummaryRecord,
    SQLiteIngestionStore,
    utc_now,
)


class MetadataJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_book_summary()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_enqueue_metadata_jobs_creates_tag_and_genre_jobs(self) -> None:
        """Verify summary completion can enqueue both metadata job types.
        The jobs preserve source summary provenance and generation model so the
        later worker knows exactly which stored summary to use.
        """
        enqueued = enqueue_metadata_jobs(
            EnqueueMetadataJobsOptions(
                database_url=self.database_url,
                book_id="book-1",
                source_summary_provider="codex",
                source_summary_model="codex",
                source_summary_detail="medium",
                generation_provider="ollama",
                generation_model="llama3.2:3b",
            )
        )

        with SQLiteIngestionStore(self.database_path) as store:
            jobs = store.list_metadata_jobs(status="pending")

        self.assertEqual(enqueued, 2)
        self.assertEqual([job.job_type for job in jobs], ["tags", "genres"])
        self.assertEqual(jobs[0].source_summary_provider, "codex")
        self.assertEqual(jobs[0].generation_provider, "ollama")

    def test_process_metadata_jobs_generates_tags_and_genres(self) -> None:
        """Verify the metadata worker consumes queued tag and genre work.
        The worker should dispatch to the existing metadata services and mark
        both jobs completed when generation succeeds.
        """
        enqueue_metadata_jobs(
            EnqueueMetadataJobsOptions(
                database_url=self.database_url,
                book_id="book-1",
                source_summary_provider="codex",
                source_summary_model="codex",
                source_summary_detail="medium",
                generation_provider="codex",
                generation_model="codex",
            )
        )

        with patch(
            "librarian_metadata.jobs.generate_book_tags",
            return_value=_FakeTagResult(generated_tags=2, cached_tags=0),
        ) as tag_generator, patch(
            "librarian_metadata.jobs.generate_book_genres",
            return_value=_FakeGenreResult(generated_genres=1, cached_genres=0),
        ) as genre_generator:
            result = process_metadata_jobs(
                ProcessMetadataJobsOptions(database_url=self.database_url, limit=5)
            )

        with SQLiteIngestionStore(self.database_path) as store:
            completed_jobs = store.list_metadata_jobs(status="completed")

        self.assertEqual(result.processed, 2)
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(completed_jobs), 2)
        self.assertTrue(all(job.started_at is not None for job in completed_jobs))
        self.assertTrue(all(job.completed_at is not None for job in completed_jobs))
        self.assertTrue(all(job.duration_seconds is not None for job in completed_jobs))
        tag_generator.assert_called_once()
        genre_generator.assert_called_once()

    def test_process_metadata_jobs_marks_failed_job_without_stopping_worker(self) -> None:
        """Verify metadata generation failures become durable job state.
        A bad model response should not lose the queued job; it should mark the
        job failed with an error that the UI or CLI can surface.
        """
        enqueue_metadata_jobs(
            EnqueueMetadataJobsOptions(
                database_url=self.database_url,
                book_id="book-1",
                source_summary_provider="codex",
                source_summary_model="codex",
                source_summary_detail="medium",
                generation_provider="codex",
                generation_model="codex",
                include_genres=False,
            )
        )

        with patch(
            "librarian_metadata.jobs.generate_book_tags",
            side_effect=RuntimeError("metadata model unavailable"),
        ):
            result = process_metadata_jobs(
                ProcessMetadataJobsOptions(database_url=self.database_url, limit=1)
            )

        with SQLiteIngestionStore(self.database_path) as store:
            failed_jobs = store.list_metadata_jobs(status="failed")

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.completed, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(failed_jobs[0].attempts, 1)
        self.assertEqual(failed_jobs[0].error_message, "metadata model unavailable")
        self.assertIsNotNone(failed_jobs[0].started_at)
        self.assertIsNotNone(failed_jobs[0].completed_at)
        self.assertIsNotNone(failed_jobs[0].duration_seconds)

    def test_process_metadata_jobs_recovers_interrupted_running_jobs(self) -> None:
        """Verify restarted metadata workers automatically retry interrupted jobs.
        If tag or genre generation is killed mid-run, the next worker pass should
        move the running job back to pending and process it.
        """
        enqueue_metadata_jobs(
            EnqueueMetadataJobsOptions(
                database_url=self.database_url,
                book_id="book-1",
                source_summary_provider="codex",
                source_summary_model="codex",
                source_summary_detail="medium",
                generation_provider="codex",
                generation_model="codex",
                include_genres=False,
            )
        )
        with SQLiteIngestionStore(self.database_path) as store:
            job = store.list_metadata_jobs(status="pending")[0]
            store.claim_metadata_job(job.id, attempts=1)

        with patch(
            "librarian_metadata.jobs.generate_book_tags",
            return_value=_FakeTagResult(generated_tags=1, cached_tags=0),
        ):
            result = process_metadata_jobs(
                ProcessMetadataJobsOptions(database_url=self.database_url, limit=1)
            )

        with SQLiteIngestionStore(self.database_path) as store:
            completed_jobs = store.list_metadata_jobs(status="completed")

        self.assertEqual(result.processed, 1)
        self.assertEqual(result.completed, 1)
        self.assertEqual(completed_jobs[0].job_type, "tags")
        self.assertEqual(completed_jobs[0].attempts, 2)

    def test_metadata_job_worker_processes_until_idle(self) -> None:
        """Verify watch-mode metadata processing drains jobs then exits idle.
        This gives the future app runtime a tested loop for background tag and
        genre generation without requiring an infinite worker in tests.
        """
        enqueue_metadata_jobs(
            EnqueueMetadataJobsOptions(
                database_url=self.database_url,
                book_id="book-1",
                source_summary_provider="codex",
                source_summary_model="codex",
                source_summary_detail="medium",
                generation_provider="codex",
                generation_model="codex",
                include_genres=False,
            )
        )
        sleeps: list[float] = []

        with patch(
            "librarian_metadata.jobs.generate_book_tags",
            return_value=_FakeTagResult(generated_tags=1, cached_tags=0),
        ):
            result = run_metadata_job_worker(
                MetadataJobWorkerOptions(
                    database_url=self.database_url,
                    limit=1,
                    poll_interval_seconds=0.25,
                    idle_exit_after=1,
                ),
                sleep=sleeps.append,
            )

        self.assertEqual(result.cycles, 2)
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.idle_cycles, 1)
        self.assertEqual(sleeps, [0.25])

    def _seed_book_summary(self) -> None:
        book = BookRecord(
            id="book-1",
            source_path="/books/forward.epub",
            relative_path="forward.epub",
            file_hash="book-1",
            size_bytes=100,
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            status="ingested",
            ingested_at=utc_now(),
        )
        summary = BookSummaryRecord(
            id="summary-1",
            book_id="book-1",
            provider="codex",
            model="codex",
            detail="medium",
            source_hash="source",
            summary="Hari Seldon develops psychohistory during imperial decline.",
            chapter_summary_count=2,
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_book_summary(summary)


@dataclass(frozen=True)
class _FakeTagResult:
    generated_tags: int
    cached_tags: int


@dataclass(frozen=True)
class _FakeGenreResult:
    generated_genres: int
    cached_genres: int


if __name__ == "__main__":
    unittest.main()
