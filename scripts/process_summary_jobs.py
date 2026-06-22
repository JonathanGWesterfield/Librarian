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

from librarian_config.config import DATABASE_URL_ENV
from librarian_logging import configure_cli_logging, emit_json
from librarian_summarization.jobs import (
    ProcessSummaryJobsOptions,
    process_summary_jobs,
)

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_cli_logging()
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
        help="Maximum pending summary jobs to process.",
    )
    parser.add_argument(
        "--include-chapter-summaries",
        action="store_true",
        help="Include chapter summaries in worker result payloads.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = process_summary_jobs(
            ProcessSummaryJobsOptions(
                database_url=args.database_url,
                limit=args.limit,
                include_chapter_summaries=args.include_chapter_summaries,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        LOGGER.error("Error: %s", error)
        return 2

    payload = result.to_dict()
    if args.json:
        emit_json(payload)
        return 0

    LOGGER.info("Librarian summary job worker")
    LOGGER.info("Database: %s", result.database_url)
    LOGGER.info("Requested limit: %s", result.requested_limit)
    LOGGER.info("Processed: %s", result.processed)
    LOGGER.info("Completed: %s", result.completed)
    LOGGER.info("Failed: %s", result.failed)
    for job in result.jobs:
        title = job.title or job.book_id
        message = f" - {job.message}" if job.message else ""
        LOGGER.info(
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
