#!/usr/bin/env python3
"""Developer playground CLI for inspecting and processing summary jobs.

This script is a hands-on wrapper around Librarian's durable summary job queue.
Ingestion can enqueue summary jobs after EPUB parsing/chunking, and this script
lets you list those queued jobs or process a small batch without starting a
desktop app. Product code should call the package service or FastAPI endpoint
once those surfaces exist; this file is deliberately for local development.

Use this when you want to see whether ingestion queued work, inspect failed
summary jobs, or manually drain a few pending jobs while testing Codex/Ollama
summary generation.

Examples:

List pending summary jobs:
    python3 scripts/play/summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      list

List failed summary jobs as JSON:
    python3 scripts/play/summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      list \\
      --status failed \\
      --json

Process one pending summary job:
    python3 scripts/play/summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      process

Process up to five pending summary jobs:
    python3 scripts/play/summary_jobs.py \\
      --database-url sqlite:///data/librarian.db \\
      process \\
      --limit 5
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_config.config import (
    CHUNK_SUMMARY_TIMEOUT_SECONDS_ENV,
    DATABASE_URL_ENV,
    MAX_PARALLEL_CHUNK_SUMMARIES_ENV,
    resolve_database_url,
)
from librarian_logging import configure_cli_logging, emit_json
from librarian_storage.storage import create_ingestion_store
from librarian_summarization.jobs import (
    ProcessSummaryJobsOptions,
    process_summary_jobs,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and process Librarian summary jobs."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List queued summary jobs.")
    list_parser.add_argument(
        "--status",
        choices=["pending", "running", "completed", "failed"],
        help="Filter jobs by status.",
    )
    list_parser.add_argument("--book-id", help="Filter jobs by exact stored book id.")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum jobs to show.",
    )
    _add_json_flag(list_parser)

    process_parser = subparsers.add_parser(
        "process",
        help="Process pending summary jobs.",
    )
    process_parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum pending jobs to process.",
    )
    process_parser.add_argument(
        "--include-chapter-summaries",
        action="store_true",
        help="Include chapter summaries in worker result payloads.",
    )
    process_parser.add_argument(
        "--chunk-summary-timeout-seconds",
        type=float,
        help=(
            "Timeout for each Codex chunk/chapter summary call instead of "
            f"{CHUNK_SUMMARY_TIMEOUT_SECONDS_ENV}."
        ),
    )
    process_parser.add_argument(
        "--max-parallel-chunk-summaries",
        type=int,
        help=(
            "Maximum chunk/chapter summaries to generate concurrently instead "
            f"of {MAX_PARALLEL_CHUNK_SUMMARIES_ENV}."
        ),
    )
    _add_json_flag(process_parser)

    args = parser.parse_args(argv)
    configure_cli_logging(console=not args.json)
    database_url = resolve_database_url(args.database_url)

    try:
        if args.command == "list":
            jobs = _list_jobs(
                database_url,
                status=args.status,
                book_id=args.book_id,
                limit=args.limit,
            )
            if args.json:
                emit_json(jobs)
            else:
                _log_jobs(jobs)
            return 0

        if args.command == "process":
            result = process_summary_jobs(
                ProcessSummaryJobsOptions(
                    database_url=database_url,
                    limit=args.limit,
                    include_chapter_summaries=args.include_chapter_summaries,
                    chunk_summary_timeout_seconds=args.chunk_summary_timeout_seconds,
                    max_parallel_chunk_summaries=args.max_parallel_chunk_summaries,
                )
            )
            payload = result.to_dict()
            if args.json:
                emit_json(payload)
            else:
                _log_process_result(payload)
            return 0
    except (ValueError, NotImplementedError, RuntimeError) as error:
        logger.error("Error: %s", error)
        return 2

    parser.error(f"unsupported command: {args.command}")
    return 2


def _list_jobs(
    database_url: str,
    *,
    status: str | None,
    book_id: str | None,
    limit: int,
) -> list[dict[str, object]]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return [
            asdict(job)
            for job in store.list_summary_jobs(
                status=status,
                book_id=book_id,
                limit=max(1, limit),
            )
        ]
    finally:
        store.close()


def _log_jobs(jobs: list[dict[str, object]]) -> None:
    if not jobs:
        logger.info("No summary jobs found.")
        return
    for job in jobs:
        title = job["title"] or job["relative_path"] or job["book_id"]
        error = f" - {job['error_message']}" if job.get("error_message") else ""
        logger.info(
            f"- [{job['status']}] {title} "
            f"({job['provider']}/{job['model']}/{job['detail']}, "
            f"attempts={job['attempts']}){error}"
        )


def _log_process_result(payload: dict[str, object]) -> None:
    logger.info("Librarian summary job worker")
    logger.info("Database: %s", payload["database_url"])
    logger.info("Requested limit: %s", payload["requested_limit"])
    logger.info("Processed: %s", payload["processed"])
    logger.info("Completed: %s", payload["completed"])
    logger.info("Failed: %s", payload["failed"])
    jobs = payload.get("jobs", [])
    if isinstance(jobs, list):
        _log_jobs(jobs)


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


if __name__ == "__main__":
    raise SystemExit(main())
