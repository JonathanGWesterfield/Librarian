#!/usr/bin/env python3
"""Index stored Librarian chunks into local OpenSearch.

This script copies searchable chunk documents from SQLite into OpenSearch. SQLite
remains the source of truth for books, chunks, embeddings, summaries, tags, and
genres; OpenSearch is a rebuildable query index for faster hybrid retrieval.

Run this after EPUB ingestion and embedding generation. Re-run it after changing
the embedding model, re-chunking books, regenerating tags/genres, or deleting
books.

Examples:

Index current chunks with default settings:
    python3 scripts/index_opensearch.py

Rebuild the local development index from scratch:
    python3 scripts/index_opensearch.py \\
      --database-url sqlite:///data/librarian.db \\
      --opensearch-url http://localhost:9200 \\
      --index-name librarian-chunks \\
      --embedding-provider ollama \\
      --embedding-model all-minilm \\
      --reset

Emit machine-readable JSON:
    python3 scripts/index_opensearch.py \\
      --database-url sqlite:///data/librarian.db \\
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

from librarian_config.config import (  # noqa: E402
    DATABASE_URL_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_PROVIDER_ENV,
    OPENSEARCH_INDEX_ENV,
    OPENSEARCH_URL_ENV,
)
from librarian_logging import configure_cli_logging, emit_json  # noqa: E402
from librarian_search.opensearch import (  # noqa: E402
    OpenSearchError,
    OpenSearchIndexOptions,
    index_chunks,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Index stored Librarian chunks into OpenSearch."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--opensearch-url",
        help=f"Override the OpenSearch URL instead of {OPENSEARCH_URL_ENV}.",
    )
    parser.add_argument(
        "--index-name",
        help=f"Override the OpenSearch index instead of {OPENSEARCH_INDEX_ENV}.",
    )
    parser.add_argument(
        "--embedding-provider",
        default="ollama",
        help=f"Embedding provider to index instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    parser.add_argument(
        "--embedding-model",
        default="all-minilm",
        help=f"Embedding model to index instead of {EMBEDDING_MODEL_ENV}.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Number of documents per OpenSearch bulk request.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the target index before indexing.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    configure_cli_logging(console=not args.json)

    try:
        result = index_chunks(
            OpenSearchIndexOptions(
                database_url=args.database_url,
                opensearch_url=args.opensearch_url,
                index_name=args.index_name,
                embedding_provider=args.embedding_provider,
                embedding_model=args.embedding_model,
                reset=args.reset,
                batch_size=args.batch_size,
            )
        )
    except (ValueError, NotImplementedError, OpenSearchError) as error:
        logger.error("Error: %s", error)
        return 2

    payload = result.to_dict()
    if args.json:
        emit_json(payload)
        return 0

    logger.info("Librarian OpenSearch indexing")
    logger.info("Database: %s", result.database_url)
    logger.info("OpenSearch: %s", result.opensearch_url)
    logger.info("Index: %s", result.index_name)
    logger.info(
        "Embedding: %s/%s (%s dimensions)",
        result.embedding_provider,
        result.embedding_model,
        result.dimensions,
    )
    logger.info("Documents seen: %s", result.documents_seen)
    logger.info("Documents indexed: %s", result.documents_indexed)
    logger.info("Reset index: %s", result.reset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
