from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
import time
from collections.abc import Callable

from librarian_config.config import resolve_database_url
from librarian_storage.storage import StoredSummaryJobRecord, create_ingestion_store
from librarian_summarization.summarize import (
    SummarizeBookOptions,
    SummaryProgress,
    summarize_book,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessSummaryJobsOptions:
    database_url: str | None = None
    limit: int = 1
    include_chapter_summaries: bool = False
    chunk_summary_timeout_seconds: float | None = None
    max_parallel_chunk_summaries: int | None = None


@dataclass(frozen=True)
class SummaryJobWorkerOptions:
    database_url: str | None = None
    limit: int = 1
    poll_interval_seconds: float = 5.0
    max_cycles: int | None = None
    idle_exit_after: int | None = None
    include_chapter_summaries: bool = False
    chunk_summary_timeout_seconds: float | None = None
    max_parallel_chunk_summaries: int | None = None


@dataclass(frozen=True)
class SummaryJobProcessResult:
    job_id: str
    book_id: str
    title: str | None
    provider: str
    model: str
    detail: str
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SummaryJobRunResult:
    database_url: str
    requested_limit: int
    processed: int
    completed: int
    failed: int
    jobs: list[SummaryJobProcessResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["jobs"] = [job.to_dict() for job in self.jobs]
        return payload


@dataclass(frozen=True)
class SummaryJobWorkerResult:
    database_url: str
    cycles: int
    requested_limit: int
    processed: int
    completed: int
    failed: int
    idle_cycles: int
    jobs: list[SummaryJobProcessResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["jobs"] = [job.to_dict() for job in self.jobs]
        return payload


def process_summary_jobs(
    options: ProcessSummaryJobsOptions | None = None,
) -> SummaryJobRunResult:
    options = options or ProcessSummaryJobsOptions()
    database_url = resolve_database_url(options.database_url)
    requested_limit = max(1, options.limit)
    pending_jobs = _list_pending_jobs(database_url, limit=requested_limit)

    results: list[SummaryJobProcessResult] = []
    completed_count = 0
    failed_count = 0
    for job in pending_jobs:
        attempts = job.attempts + 1
        if not _claim_job(database_url, job.id, attempts=attempts):
            logger.info("Skipping summary job already claimed by another worker: %s", job.id)
            continue

        logger.info(
            "Processing summary job %s for %s provider=%s model=%s detail=%s attempt=%s",
            job.id,
            job.title or job.relative_path,
            job.provider,
            job.model,
            job.detail,
            attempts,
        )

        try:
            summary = summarize_book(
                SummarizeBookOptions(
                    database_url=database_url,
                    book_id=job.book_id,
                    generation_provider=job.provider,
                    generation_model=job.model,
                    detail=job.detail,
                    include_chapter_summaries=options.include_chapter_summaries,
                    chunk_summary_timeout_seconds=options.chunk_summary_timeout_seconds,
                    max_parallel_chunk_summaries=options.max_parallel_chunk_summaries,
                    progress_callback=_job_progress_callback(database_url, job),
                )
            )
        except Exception as error:
            message = str(error)
            logger.exception(
                "Summary job %s failed for %s: %s",
                job.id,
                job.title or job.relative_path,
                message,
            )
            _update_job(
                database_url,
                job.id,
                status="failed",
                attempts=attempts,
                error_message=message,
            )
            failed_count += 1
            results.append(
                _job_result(
                    job,
                    status="failed",
                    message=message,
                )
            )
            continue

        message = (
            f"{summary.generated_chapter_summaries} chapter summaries generated, "
            f"{summary.cached_chapter_summaries} reused"
        )
        _update_job_progress(
            database_url,
            job.id,
            SummaryProgress(
                stage="completed",
                current=summary.chapter_summary_count,
                total=summary.chapter_summary_count,
                message=message,
            ),
        )
        _update_job(
            database_url,
            job.id,
            status="completed",
            attempts=attempts,
            error_message=None,
        )
        completed_count += 1
        results.append(
            _job_result(
                job,
                status="completed",
                message=message,
            )
        )

    return SummaryJobRunResult(
        database_url=database_url,
        requested_limit=requested_limit,
        processed=len(results),
        completed=completed_count,
        failed=failed_count,
        jobs=results,
    )


def run_summary_job_worker(
    options: SummaryJobWorkerOptions | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> SummaryJobWorkerResult:
    options = options or SummaryJobWorkerOptions()
    database_url = resolve_database_url(options.database_url)
    requested_limit = max(1, options.limit)
    poll_interval_seconds = max(0.0, options.poll_interval_seconds)
    max_cycles = options.max_cycles
    idle_exit_after = options.idle_exit_after

    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be greater than zero")
    if idle_exit_after is not None and idle_exit_after < 1:
        raise ValueError("idle_exit_after must be greater than zero")

    cycles = 0
    idle_cycles = 0
    processed = 0
    completed = 0
    failed = 0
    jobs: list[SummaryJobProcessResult] = []

    logger.info(
        "Starting summary job worker database=%s limit=%s poll_interval=%.2fs",
        database_url,
        requested_limit,
        poll_interval_seconds,
    )

    while True:
        cycles += 1
        run_result = process_summary_jobs(
            ProcessSummaryJobsOptions(
                database_url=database_url,
                limit=requested_limit,
                include_chapter_summaries=options.include_chapter_summaries,
                chunk_summary_timeout_seconds=options.chunk_summary_timeout_seconds,
                max_parallel_chunk_summaries=options.max_parallel_chunk_summaries,
            )
        )
        processed += run_result.processed
        completed += run_result.completed
        failed += run_result.failed
        jobs.extend(run_result.jobs)

        if run_result.processed:
            idle_cycles = 0
            logger.info(
                "Summary worker cycle %s processed=%s completed=%s failed=%s",
                cycles,
                run_result.processed,
                run_result.completed,
                run_result.failed,
            )
        else:
            idle_cycles += 1
            logger.info("Summary worker cycle %s found no pending jobs", cycles)

        if max_cycles is not None and cycles >= max_cycles:
            break
        if idle_exit_after is not None and idle_cycles >= idle_exit_after:
            break

        if poll_interval_seconds:
            sleep(poll_interval_seconds)

    return SummaryJobWorkerResult(
        database_url=database_url,
        cycles=cycles,
        requested_limit=requested_limit,
        processed=processed,
        completed=completed,
        failed=failed,
        idle_cycles=idle_cycles,
        jobs=jobs,
    )


def _list_pending_jobs(
    database_url: str, *, limit: int
) -> list[StoredSummaryJobRecord]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return store.list_summary_jobs(status="pending", limit=limit)
    finally:
        store.close()


def _claim_job(database_url: str, job_id: str, *, attempts: int) -> bool:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return store.claim_summary_job(job_id, attempts=attempts)
    finally:
        store.close()


def _update_job(
    database_url: str,
    job_id: str,
    *,
    status: str,
    attempts: int,
    error_message: str | None,
) -> None:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        store.update_summary_job(
            job_id,
            status=status,
            attempts=attempts,
            error_message=error_message,
        )
    finally:
        store.close()


def _update_job_progress(
    database_url: str, job_id: str, progress: SummaryProgress
) -> None:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        store.update_summary_job_progress(
            job_id,
            stage=progress.stage,
            current_step=progress.current,
            total_steps=progress.total,
            message=progress.message,
        )
    finally:
        store.close()


def _job_progress_callback(
    database_url: str, job: StoredSummaryJobRecord
) -> Callable[[SummaryProgress], None]:
    def _callback(progress: SummaryProgress) -> None:
        logger.info(
            "Summary job %s %s/%s stage=%s book=%s provider=%s model=%s: %s",
            job.id,
            progress.current,
            progress.total,
            progress.stage,
            job.title or job.relative_path,
            job.provider,
            job.model,
            progress.message,
        )
        _update_job_progress(database_url, job.id, progress)

    return _callback


def _job_result(
    job: StoredSummaryJobRecord, *, status: str, message: str | None
) -> SummaryJobProcessResult:
    return SummaryJobProcessResult(
        job_id=job.id,
        book_id=job.book_id,
        title=job.title,
        provider=job.provider,
        model=job.model,
        detail=job.detail,
        status=status,
        message=message,
    )
