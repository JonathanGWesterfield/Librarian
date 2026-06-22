#!/usr/bin/env python3
"""Playground wrapper for the canonical EPUB ingestion workflow.

This script exists for direct local and batch ingestion while developing the
ingestion pipeline. It delegates the real parse/chunk/store behavior to
librarian_ingestion.ingest.run_ingestion, which is also used by API and other
entrypoints. It is kept under scripts/play because it is a developer convenience
tool rather than the intended product surface.

Use this when you want to quickly scan EPUBs, populate the local SQLite
database, optionally generate embeddings during ingestion, or inspect ingestion
summary output without calling FastAPI.

Examples:

Ingest EPUBs from the configured source directory:
    python3 scripts/play/ingest_epubs.py \\
      --database-url sqlite:///data/librarian.db

Ingest EPUBs from an explicit local directory and include discovered files:
    python3 scripts/play/ingest_epubs.py \\
      --books-dir ./Epub-Books \\
      --database-url sqlite:///data/librarian.db \\
      --list

Force re-parse unchanged EPUBs and generate Ollama embeddings:
    python3 scripts/play/ingest_epubs.py \\
      --books-dir ./Epub-Books \\
      --database-url sqlite:///data/librarian.db \\
      --force \\
      --embed \\
      --embedding-provider ollama \\
      --embedding-model all-minilm

Ingest EPUBs and queue asynchronous summary jobs:
    python3 scripts/play/ingest_epubs.py \\
      --books-dir ./Epub-Books \\
      --database-url sqlite:///data/librarian.db \\
      --enqueue-summaries \\
      --summary-generation-provider codex \\
      --summary-generation-model codex

Return machine-readable JSON for inspection:
    python3 scripts/play/ingest_epubs.py \\
      --books-dir ./Epub-Books \\
      --database-url sqlite:///data/librarian.db \\
      --json
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_config.config import (
    BOOKS_DIR_ENV,
    DATABASE_URL_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_PROVIDER_ENV,
    GENERATION_MODEL_ENV,
    GENERATION_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
)
from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_ingestion.scan import EpubSourceError
from librarian_logging import configure_cli_logging, emit_json

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_cli_logging()
    parser = argparse.ArgumentParser(
        description="Scan the configured Librarian EPUB directory."
    )
    parser.add_argument(
        "--books-dir",
        help=f"Override the EPUB source directory instead of {BOOKS_DIR_ENV}.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print each discovered EPUB with size and SHA-256 hash.",
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the ingestion database instead of {DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-parse and store unchanged EPUB files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON for desktop apps and automation.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate and store chunk embeddings during ingestion.",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["noop", "ollama"],
        help=f"Embedding provider override instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    parser.add_argument(
        "--embedding-model",
        help=f"Embedding model override instead of {EMBEDDING_MODEL_ENV}.",
    )
    parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=16,
        help="Number of chunks to send to the embedder per request.",
    )
    parser.add_argument(
        "--enqueue-summaries",
        action="store_true",
        help="Queue asynchronous chapter/book summary jobs for newly ingested books.",
    )
    parser.add_argument(
        "--summary-generation-provider",
        choices=["noop", "ollama", "codex"],
        help=f"Summary provider override instead of {GENERATION_PROVIDER_ENV}.",
    )
    parser.add_argument(
        "--summary-generation-model",
        help=f"Summary model override instead of {GENERATION_MODEL_ENV}.",
    )
    parser.add_argument(
        "--summary-detail",
        choices=["short", "medium", "detailed"],
        default="medium",
        help="Queued summary detail level.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_ingestion(
            IngestionOptions(
                books_dir=args.books_dir,
                database_url=args.database_url,
                force=args.force,
                list_epubs=args.list,
                embed_chunks=args.embed,
                embedding_provider=args.embedding_provider,
                embedding_model=args.embedding_model,
                ollama_base_url=args.ollama_base_url,
                embedding_batch_size=args.embedding_batch_size,
                enqueue_summaries=args.enqueue_summaries,
                summary_generation_provider=args.summary_generation_provider,
                summary_generation_model=args.summary_generation_model,
                summary_detail=args.summary_detail,
            )
        )
    except (EpubSourceError, ValueError, NotImplementedError) as error:
        logger.error("Error: %s", error)
        return 2

    if args.json:
        emit_json(result.to_dict())
        return 0

    logger.info("Librarian EPUB ingestion")
    logger.info("Books directory: %s", result.books_dir)
    logger.info("Database: %s", result.database_url)
    logger.info("Embedding provider: %s", result.embedding_provider)
    logger.info("Embedding model: %s", result.embedding_model)
    logger.info("Found %s EPUB files", result.found)

    if args.list:
        for epub in result.discovered:
            logger.info(
                "- %s (%s bytes, sha256=%s)",
                epub["relative_path"],
                epub["size_bytes"],
                epub["sha256"],
            )

    for book in result.books:
        if book.status == "failed":
            logger.error("Failed %s: %s", book.relative_path, book.message)

    logger.info("Parsed %s", result.parsed)
    logger.info("Skipped unchanged %s", result.skipped_unchanged)
    logger.info("Skipped duplicates %s", result.skipped_duplicates)
    logger.info("Failed %s", result.failed)
    logger.info("Stored chunks %s", result.stored_chunks)
    logger.info("Stored embeddings %s", result.stored_embeddings)
    logger.info("Queued summary jobs %s", result.summary_jobs_enqueued)
    logger.info(
        "Database totals: "
        f"{result.total_books} books, "
        f"{result.total_chunks} chunks, "
        f"{result.total_embeddings} embeddings"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
