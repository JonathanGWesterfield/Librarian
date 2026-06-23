#!/usr/bin/env python3
"""Process queued book metadata jobs from the local Librarian database.

Summary generation can enqueue metadata jobs after a book summary is completed.
This worker drains those durable jobs later, calling the existing tag and genre
generation services. It does not summarize books and it does not ingest EPUBs;
it assumes the target book already has the summary referenced by the job.

Use this when you want tags and genres to fill in after summary jobs complete,
run a small batch while testing metadata prompts, or recover pending metadata
jobs after restarting the local app.

Examples:

Process one pending metadata job from the default database:
    python3 scripts/process_metadata_jobs.py

Process up to five metadata jobs from the local development database:
    python3 scripts/process_metadata_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --limit 5

Process only tag jobs:
    python3 scripts/process_metadata_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --job-type tags

Run a polling worker until it observes three idle cycles:
    python3 scripts/process_metadata_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      --watch \\
      --idle-exit-after 3

Emit machine-readable JSON for automation:
    python3 scripts/process_metadata_jobs.py \\
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

from librarian_config.config import DATABASE_URL_ENV
from librarian_logging import configure_cli_logging, emit_json
from librarian_metadata.jobs import (
    METADATA_JOB_TYPE_GENRES,
    METADATA_JOB_TYPE_TAGS,
    MetadataJobWorkerOptions,
    ProcessMetadataJobsOptions,
    process_metadata_jobs,
    run_metadata_job_worker,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process queued Librarian tag and genre metadata jobs."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum pending metadata jobs to process per cycle.",
    )
    parser.add_argument(
        "--job-type",
        choices=[METADATA_JOB_TYPE_TAGS, METADATA_JOB_TYPE_GENRES],
        help="Only process one metadata job type.",
    )
    parser.add_argument(
        "--max-tags",
        type=int,
        default=12,
        help="Maximum topic tags to generate for tag jobs.",
    )
    parser.add_argument(
        "--max-secondary-genres",
        type=int,
        default=3,
        help="Maximum secondary genres to generate for genre jobs.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep polling for pending metadata jobs instead of running one batch.",
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    configure_cli_logging(console=not args.json)

    try:
        if args.watch:
            result = run_metadata_job_worker(
                MetadataJobWorkerOptions(
                    database_url=args.database_url,
                    limit=args.limit,
                    poll_interval_seconds=args.poll_interval_seconds,
                    max_cycles=args.max_cycles,
                    idle_exit_after=args.idle_exit_after,
                    job_type=args.job_type,
                    max_tags=args.max_tags,
                    max_secondary_genres=args.max_secondary_genres,
                )
            )
        else:
            result = process_metadata_jobs(
                ProcessMetadataJobsOptions(
                    database_url=args.database_url,
                    limit=args.limit,
                    job_type=args.job_type,
                    max_tags=args.max_tags,
                    max_secondary_genres=args.max_secondary_genres,
                )
            )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        logger.error("Error: %s", error)
        return 2

    payload = result.to_dict()
    if args.json:
        emit_json(payload)
        return 0

    logger.info("Librarian metadata job worker")
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
            "- [%s] %s %s (%s/%s)%s",
            job.status,
            job.job_type,
            title,
            job.provider,
            job.model,
            message,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
