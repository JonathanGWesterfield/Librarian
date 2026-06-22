from __future__ import annotations

from dataclasses import asdict, dataclass, field

from librarian_config.config import resolve_database_url
from librarian_storage.storage import StoredSummaryJobRecord, create_ingestion_store
from librarian_summarization.summarize import SummarizeBookOptions, summarize_book


@dataclass(frozen=True)
class ProcessSummaryJobsOptions:
    database_url: str | None = None
    limit: int = 1
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
        _update_job(
            database_url,
            job.id,
            status="running",
            attempts=attempts,
            error_message=None,
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
                )
            )
        except Exception as error:
            message = str(error)
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
                message=(
                    f"{summary.generated_chapter_summaries} chapter summaries "
                    f"generated, {summary.cached_chapter_summaries} reused"
                ),
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


def _list_pending_jobs(
    database_url: str, *, limit: int
) -> list[StoredSummaryJobRecord]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return store.list_summary_jobs(status="pending", limit=limit)
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
