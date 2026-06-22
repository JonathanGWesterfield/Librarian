#!/usr/bin/env python3
"""Developer CLI for on-demand book and chapter summarization.

This script is intentionally a narrow, single-book tool. It does not ingest EPUBs
and it does not scan a directory of books. Instead, it reads chunks that already
exist in the configured Librarian SQLite database, generates or reuses cached
chapter summaries, and then synthesizes a book-level summary.

Use this when you want to manually inspect summary quality, rebuild summaries
with a different generation provider/model, or clear cached summaries before a
benchmark. Batch summarization can be composed by running this script once per
book, including in parallel, while keeping this command easy to debug.

Examples:

Generate a human-readable Codex summary for one ingested book:
    python3 scripts/summarize.py \\
      --database-url sqlite:///data/librarian.db \\
      book \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov" \\
      --generation-provider codex \\
      --generation-model codex \\
      --detail medium

Return machine-readable JSON for automation or inspection:
    python3 scripts/summarize.py \\
      --database-url sqlite:///data/librarian.db \\
      book \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov" \\
      --generation-provider codex \\
      --json

Reset and rebuild summaries with an Ollama model:
    python3 scripts/summarize.py \\
      --database-url sqlite:///data/librarian.db \\
      book \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov" \\
      --generation-provider ollama \\
      --generation-model llama3.2:3b \\
      --detail medium \\
      --reset

Delete cached summaries for a provider/model/detail combination:
    python3 scripts/summarize.py \\
      --database-url sqlite:///data/librarian.db \\
      delete \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov" \\
      --generation-provider codex \\
      --generation-model codex \\
      --detail medium
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_config.config import (
    DATABASE_URL_ENV,
    GENERATION_MODEL_ENV,
    GENERATION_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
)
from librarian_logging import configure_cli_logging, emit_json
from librarian_summarization.summarize import (
    DeleteSummariesOptions,
    SummaryProgress,
    SummarizeBookOptions,
    delete_summaries,
    summarize_book,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_cli_logging()
    parser = argparse.ArgumentParser(
        description="Summarize one ingested book from local chunks."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize_parser = subparsers.add_parser(
        "book",
        help="Generate or reuse chapter summaries, then synthesize a book summary.",
    )
    _add_book_filters(summarize_parser)
    _add_generation_options(summarize_parser)
    summarize_parser.add_argument(
        "--detail",
        choices=["short", "medium", "detailed"],
        default="medium",
        help="Summary detail level.",
    )
    summarize_parser.add_argument(
        "--chunks-per-section",
        type=int,
        default=8,
        help="Fallback window size when chapter metadata is unavailable.",
    )
    summarize_parser.add_argument(
        "--max-section-chars",
        type=int,
        default=12000,
        help="Maximum source characters to send in one section summary prompt.",
    )
    summarize_parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Regenerate summaries even when cached source hashes match.",
    )
    summarize_parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete matching summaries before regenerating them.",
    )
    summarize_parser.add_argument(
        "--no-chapter-summaries",
        action="store_true",
        help="Hide chapter summaries in the printed/JSON response.",
    )
    summarize_parser.add_argument("--json", action="store_true")

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete stored summaries so a provider/model can be rebuilt.",
    )
    _add_book_filters(delete_parser)
    _add_generation_options(delete_parser)
    delete_parser.add_argument(
        "--detail",
        choices=["short", "medium", "detailed"],
        help="Only delete summaries for this detail level.",
    )
    delete_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "book":
            result = summarize_book(
                SummarizeBookOptions(
                    database_url=args.database_url,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    generation_provider=args.generation_provider,
                    generation_model=args.generation_model,
                    ollama_base_url=args.ollama_base_url,
                    detail=args.detail,
                    chunks_per_section=args.chunks_per_section,
                    max_section_chars=args.max_section_chars,
                    force_refresh=args.force_refresh,
                    reset=args.reset,
                    include_chapter_summaries=not args.no_chapter_summaries,
                    progress_callback=None if args.json else _print_progress,
                )
            )
            payload = result.to_dict()
            if args.json:
                emit_json(payload)
            else:
                _log_summary(payload)
            return 0
        if args.command == "delete":
            result = delete_summaries(
                DeleteSummariesOptions(
                    database_url=args.database_url,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    generation_provider=args.generation_provider,
                    generation_model=args.generation_model,
                    detail=args.detail,
                )
            )
            payload = result.to_dict()
            if args.json:
                emit_json(payload)
            else:
                logger.info("Deleted summaries: %s", payload["deleted_summaries"])
            return 0
    except (ValueError, NotImplementedError, RuntimeError) as error:
        logger.error("Error: %s", error)
        return 2

    parser.error(f"unsupported command: {args.command}")
    return 2


def _add_book_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--book-id", help="Summarize one exact stored book id.")
    parser.add_argument("--book-title", help="Summarize a matching book title.")
    parser.add_argument("--author", help="Restrict title lookup to this author.")


def _add_generation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--generation-provider",
        choices=["noop", "ollama", "codex"],
        help=f"Generation provider override instead of {GENERATION_PROVIDER_ENV}.",
    )
    parser.add_argument(
        "--generation-model",
        help=f"Generation model override instead of {GENERATION_MODEL_ENV}.",
    )
    parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )


def _log_summary(payload: dict[str, object]) -> None:
    logger.info("Book: %s", payload["title"] or payload["book_id"])
    logger.info("Authors: %s", ", ".join(payload["authors"]))
    logger.info("Generator: %s / %s", payload["provider"], payload["model"])
    logger.info("Detail: %s", payload["detail"])
    logger.info(
        "Chapter summaries: "
        f"{payload['chapter_summary_count']} total, "
        f"{payload['generated_chapter_summaries']} generated, "
        f"{payload['cached_chapter_summaries']} cached"
    )
    if payload["deleted_summaries"]:
        logger.info("Deleted before rebuild: %s", payload["deleted_summaries"])
    logger.info("Book summary:")
    logger.info("%s", payload["summary"])
    chapter_summaries = payload.get("chapter_summaries")
    if isinstance(chapter_summaries, list) and chapter_summaries:
        logger.info("Chapter summaries:")
        for summary in chapter_summaries:
            if not isinstance(summary, dict):
                continue
            title = summary["chapter_title"] or summary["chapter_key"]
            cache_marker = "cached" if summary["cached"] else "generated"
            logger.info(
                "- %s (chunks %s-%s, %s)",
                title,
                summary["chunk_start_index"],
                summary["chunk_end_index"],
                cache_marker,
            )
            logger.info("%s", summary["summary"])


def _print_progress(progress: SummaryProgress) -> None:
    if progress.total > 0:
        prefix = f"[{progress.stage} {progress.current}/{progress.total}]"
    else:
        prefix = f"[{progress.stage}]"
    logger.info("%s %s", prefix, progress.message)


if __name__ == "__main__":
    raise SystemExit(main())
