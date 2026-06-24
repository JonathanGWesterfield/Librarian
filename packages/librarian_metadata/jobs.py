from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import logging
import time
from collections.abc import Callable

from librarian_config.config import resolve_database_url
from librarian_metadata.genres import GenerateBookGenresOptions, generate_book_genres
from librarian_metadata.tags import GenerateBookTagsOptions, generate_book_tags
from librarian_storage.storage import (
    MetadataJobRecord,
    StoredMetadataJobRecord,
    create_ingestion_store,
)

METADATA_JOB_TYPE_TAGS = "tags"
METADATA_JOB_TYPE_GENRES = "genres"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnqueueMetadataJobsOptions:
    database_url: str | None = None
    book_id: str = ""
    source_summary_provider: str = "noop"
    source_summary_model: str = "noop"
    source_summary_detail: str = "medium"
    generation_provider: str = "noop"
    generation_model: str = "noop"
    include_tags: bool = True
    include_genres: bool = True


@dataclass(frozen=True)
class ProcessMetadataJobsOptions:
    database_url: str | None = None
    limit: int = 1
    job_type: str | None = None
    max_tags: int = 12
    max_secondary_genres: int = 3


@dataclass(frozen=True)
class MetadataJobWorkerOptions:
    database_url: str | None = None
    limit: int = 1
    poll_interval_seconds: float = 5.0
    max_cycles: int | None = None
    idle_exit_after: int | None = None
    job_type: str | None = None
    max_tags: int = 12
    max_secondary_genres: int = 3


@dataclass(frozen=True)
class MetadataJobProcessResult:
    job_id: str
    book_id: str
    title: str | None
    job_type: str
    provider: str
    model: str
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MetadataJobRunResult:
    database_url: str
    requested_limit: int
    processed: int
    completed: int
    failed: int
    jobs: list[MetadataJobProcessResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["jobs"] = [job.to_dict() for job in self.jobs]
        return payload


@dataclass(frozen=True)
class MetadataJobWorkerResult:
    database_url: str
    cycles: int
    requested_limit: int
    processed: int
    completed: int
    failed: int
    idle_cycles: int
    jobs: list[MetadataJobProcessResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["jobs"] = [job.to_dict() for job in self.jobs]
        return payload


def enqueue_metadata_jobs(options: EnqueueMetadataJobsOptions) -> int:
    database_url = resolve_database_url(options.database_url)
    jobs = _build_metadata_jobs(options)
    if not jobs:
        return 0

    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        for job in jobs:
            store.save_metadata_job(job)
    finally:
        store.close()
    return len(jobs)


def process_metadata_jobs(
    options: ProcessMetadataJobsOptions | None = None,
) -> MetadataJobRunResult:
    options = options or ProcessMetadataJobsOptions()
    database_url = resolve_database_url(options.database_url)
    requested_limit = max(1, options.limit)
    recovered_running_jobs = _requeue_running_jobs(database_url, job_type=options.job_type)
    if recovered_running_jobs:
        logger.info("Recovered %s interrupted metadata job(s)", recovered_running_jobs)
    pending_jobs = _list_pending_jobs(
        database_url, limit=requested_limit, job_type=options.job_type
    )

    results: list[MetadataJobProcessResult] = []
    completed_count = 0
    failed_count = 0
    for job in pending_jobs:
        attempts = job.attempts + 1
        if not _claim_job(database_url, job.id, attempts=attempts):
            logger.info("Skipping metadata job already claimed by another worker: %s", job.id)
            continue

        logger.info(
            "Processing metadata job %s type=%s book=%s provider=%s model=%s attempt=%s",
            job.id,
            job.job_type,
            job.title or job.relative_path,
            job.generation_provider,
            job.generation_model,
            attempts,
        )
        try:
            message = _run_job(
                job,
                database_url=database_url,
                max_tags=options.max_tags,
                max_secondary_genres=options.max_secondary_genres,
            )
        except Exception as error:
            message = str(error)
            logger.exception(
                "Metadata job %s failed for %s: %s",
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
            results.append(_job_result(job, status="failed", message=message))
            continue

        _update_job(
            database_url,
            job.id,
            status="completed",
            attempts=attempts,
            error_message=None,
        )
        completed_count += 1
        logger.info("Completed metadata job %s: %s", job.id, message)
        results.append(_job_result(job, status="completed", message=message))

    return MetadataJobRunResult(
        database_url=database_url,
        requested_limit=requested_limit,
        processed=len(results),
        completed=completed_count,
        failed=failed_count,
        jobs=results,
    )


def run_metadata_job_worker(
    options: MetadataJobWorkerOptions | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> MetadataJobWorkerResult:
    options = options or MetadataJobWorkerOptions()
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
    jobs: list[MetadataJobProcessResult] = []

    logger.info(
        "Starting metadata job worker database=%s limit=%s poll_interval=%.2fs",
        database_url,
        requested_limit,
        poll_interval_seconds,
    )

    while True:
        cycles += 1
        run_result = process_metadata_jobs(
            ProcessMetadataJobsOptions(
                database_url=database_url,
                limit=requested_limit,
                job_type=options.job_type,
                max_tags=options.max_tags,
                max_secondary_genres=options.max_secondary_genres,
            )
        )
        processed += run_result.processed
        completed += run_result.completed
        failed += run_result.failed
        jobs.extend(run_result.jobs)

        if run_result.processed:
            idle_cycles = 0
            logger.info(
                "Metadata worker cycle %s processed=%s completed=%s failed=%s",
                cycles,
                run_result.processed,
                run_result.completed,
                run_result.failed,
            )
        else:
            idle_cycles += 1
            logger.info("Metadata worker cycle %s found no pending jobs", cycles)

        if max_cycles is not None and cycles >= max_cycles:
            break
        if idle_exit_after is not None and idle_cycles >= idle_exit_after:
            break

        if poll_interval_seconds:
            sleep(poll_interval_seconds)

    return MetadataJobWorkerResult(
        database_url=database_url,
        cycles=cycles,
        requested_limit=requested_limit,
        processed=processed,
        completed=completed,
        failed=failed,
        idle_cycles=idle_cycles,
        jobs=jobs,
    )


def _run_job(
    job: StoredMetadataJobRecord,
    *,
    database_url: str,
    max_tags: int,
    max_secondary_genres: int,
) -> str:
    if job.job_type == METADATA_JOB_TYPE_TAGS:
        result = generate_book_tags(
            GenerateBookTagsOptions(
                database_url=database_url,
                book_id=job.book_id,
                source_summary_provider=job.source_summary_provider,
                source_summary_model=job.source_summary_model,
                source_summary_detail=job.source_summary_detail,
                generation_provider=job.generation_provider,
                generation_model=job.generation_model,
                max_tags=max_tags,
            )
        )
        return f"{result.generated_tags} tags generated, {result.cached_tags} reused"

    if job.job_type == METADATA_JOB_TYPE_GENRES:
        result = generate_book_genres(
            GenerateBookGenresOptions(
                database_url=database_url,
                book_id=job.book_id,
                source_summary_provider=job.source_summary_provider,
                source_summary_model=job.source_summary_model,
                source_summary_detail=job.source_summary_detail,
                generation_provider=job.generation_provider,
                generation_model=job.generation_model,
                max_secondary_genres=max_secondary_genres,
            )
        )
        return (
            f"{result.generated_genres} genres generated, "
            f"{result.cached_genres} reused"
        )

    raise ValueError(f"unsupported metadata job type: {job.job_type}")


def _build_metadata_jobs(options: EnqueueMetadataJobsOptions) -> list[MetadataJobRecord]:
    if not options.book_id:
        raise ValueError("book_id is required to enqueue metadata jobs")

    job_types: list[str] = []
    if options.include_tags:
        job_types.append(METADATA_JOB_TYPE_TAGS)
    if options.include_genres:
        job_types.append(METADATA_JOB_TYPE_GENRES)

    return [
        MetadataJobRecord(
            id=_metadata_job_id(
                book_id=options.book_id,
                job_type=job_type,
                source_summary_provider=options.source_summary_provider,
                source_summary_model=options.source_summary_model,
                source_summary_detail=options.source_summary_detail,
                generation_provider=options.generation_provider,
                generation_model=options.generation_model,
            ),
            book_id=options.book_id,
            job_type=job_type,
            source_summary_provider=options.source_summary_provider,
            source_summary_model=options.source_summary_model,
            source_summary_detail=options.source_summary_detail,
            generation_provider=options.generation_provider,
            generation_model=options.generation_model,
        )
        for job_type in job_types
    ]


def _metadata_job_id(
    *,
    book_id: str,
    job_type: str,
    source_summary_provider: str,
    source_summary_model: str,
    source_summary_detail: str,
    generation_provider: str,
    generation_model: str,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                book_id,
                job_type.strip().casefold(),
                source_summary_provider.strip().casefold(),
                source_summary_model.strip(),
                source_summary_detail.strip().casefold(),
                generation_provider.strip().casefold(),
                generation_model.strip(),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"metadata-job:{digest}"


def _list_pending_jobs(
    database_url: str, *, limit: int, job_type: str | None
) -> list[StoredMetadataJobRecord]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return store.list_metadata_jobs(
            status="pending", job_type=job_type, limit=limit
        )
    finally:
        store.close()


def _requeue_running_jobs(database_url: str, *, job_type: str | None) -> int:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return store.requeue_metadata_jobs(statuses=["running"], job_type=job_type)
    finally:
        store.close()


def _claim_job(database_url: str, job_id: str, *, attempts: int) -> bool:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return store.claim_metadata_job(job_id, attempts=attempts)
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
        store.update_metadata_job(
            job_id,
            status=status,
            attempts=attempts,
            error_message=error_message,
        )
    finally:
        store.close()


def _job_result(
    job: StoredMetadataJobRecord, *, status: str, message: str | None
) -> MetadataJobProcessResult:
    return MetadataJobProcessResult(
        job_id=job.id,
        book_id=job.book_id,
        title=job.title,
        job_type=job.job_type,
        provider=job.generation_provider,
        model=job.generation_model,
        status=status,
        message=message,
    )
