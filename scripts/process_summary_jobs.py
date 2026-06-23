#!/usr/bin/env python3
"""Process queued book summary jobs from the local Librarian database.

Ingestion can enqueue summary jobs after EPUB parsing and chunk storage without
blocking the ingest response. This worker drains those durable jobs later,
calling the existing summarization service to create chapter and book summaries.

Use this when you want to warm summary-backed metadata after ingestion, run a
small batch while testing prompt/model changes, or recover pending jobs after
restarting the local app.

Examples:

Process one pending summary job from the default database:
    python3 scripts/process_summary_jobs.py

Process up to five pending jobs from the local development database:
    python3 scripts/process_summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --limit 5

Run a polling worker until it observes three idle cycles:
    python3 scripts/process_summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --watch \\
      --idle-exit-after 3

Process summaries without queuing tag/genre jobs afterward:
    python3 scripts/process_summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --no-enqueue-metadata-jobs

Emit machine-readable JSON for automation:
    python3 scripts/process_summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --limit 5 \\
      --json
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_config.config import (
    CHUNK_SUMMARY_TIMEOUT_SECONDS_ENV,
    DATABASE_URL_ENV,
    MAX_PARALLEL_CHUNK_SUMMARIES_ENV,
)
from librarian_logging import configure_cli_logging, emit_json
from librarian_summarization.jobs import (
    ProcessSummaryJobsOptions,
    SummaryJobWorkerOptions,
    process_summary_jobs,
    run_summary_job_worker,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process queued Librarian chapter/book summary jobs."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum pending summary jobs to process per cycle.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep polling for pending summary jobs instead of running one batch.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
        help="Seconds to sleep between worker polling cycles.",
    )
    parser.add_argument(
        "--idle-exit-after",
        type=int,
        help="Stop watch mode after this many consecutive idle cycles.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        help="Stop watch mode after this many polling cycles.",
    )
    parser.add_argument(
        "--include-chapter-summaries",
        action="store_true",
        help="Include chapter summaries in worker result payloads.",
    )
    parser.add_argument(
        "--chunk-summary-timeout-seconds",
        type=float,
        help=(
            "Timeout for each Codex chunk/chapter summary call instead of "
            f"{CHUNK_SUMMARY_TIMEOUT_SECONDS_ENV}."
        ),
    )
    parser.add_argument(
        "--max-parallel-chunk-summaries",
        type=int,
        help=(
            "Maximum chunk/chapter summaries to generate concurrently instead "
            f"of {MAX_PARALLEL_CHUNK_SUMMARIES_ENV}."
        ),
    )
    parser.add_argument(
        "--no-enqueue-metadata-jobs",
        action="store_true",
        help="Do not enqueue tag/genre jobs after a summary job completes.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    configure_cli_logging(console=not args.json)

    try:
        if args.watch:
            result = run_summary_job_worker(
                SummaryJobWorkerOptions(
                    database_url=args.database_url,
                    limit=args.limit,
                    poll_interval_seconds=args.poll_interval_seconds,
                    max_cycles=args.max_cycles,
                    idle_exit_after=args.idle_exit_after,
                    include_chapter_summaries=args.include_chapter_summaries,
                    chunk_summary_timeout_seconds=args.chunk_summary_timeout_seconds,
                    max_parallel_chunk_summaries=args.max_parallel_chunk_summaries,
                    enqueue_metadata_jobs=not args.no_enqueue_metadata_jobs,
                )
            )
        else:
            result = process_summary_jobs(
                ProcessSummaryJobsOptions(
                    database_url=args.database_url,
                    limit=args.limit,
                    include_chapter_summaries=args.include_chapter_summaries,
                    chunk_summary_timeout_seconds=args.chunk_summary_timeout_seconds,
                    max_parallel_chunk_summaries=args.max_parallel_chunk_summaries,
                    enqueue_metadata_jobs=not args.no_enqueue_metadata_jobs,
                )
            )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        logger.error("Error: %s", error)
        return 2

    payload = result.to_dict()
    if args.json:
        emit_json(payload)
        return 0

    logger.info("Librarian summary job worker")
    logger.info("Database: %s", result.database_url)
    logger.info("Requested limit: %s", result.requested_limit)
    if hasattr(result, "cycles"):
        logger.info("Cycles: %s", result.cycles)
        logger.info("Idle cycles: %s", result.idle_cycles)
    logger.info("Processed: %s", result.processed)
    logger.info("Completed: %s", result.completed)
    logger.info("Failed: %s", result.failed)
    for job in result.jobs:
        title = job.title or job.book_id
        message = f" - {job.message}" if job.message else ""
        logger.info(
            "- [%s] %s (%s/%s/%s)%s",
            job.status,
            title,
            job.provider,
            job.model,
            job.detail,
            message,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
