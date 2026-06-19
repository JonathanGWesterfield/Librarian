#!/usr/bin/env python3
"""Rebuild stored chunk embeddings without deleting books or raw text.

This script operates on chunks that already exist in the Librarian SQLite
database. It is useful when benchmarking embedding models, changing providers,
or repairing missing vectors after ingestion. It can delete embeddings for one
provider/model pair or clear all embeddings before regenerating the selected
provider/model.

Use this after the local embedding provider is available. For Ollama, run
`scripts/start_local.sh` first so the model service is reachable.

Examples:

Build missing embeddings with the configured defaults:
    python3 scripts/rebuild_embeddings.py \\
      --database-url sqlite:///data/librarian.db

Reset and rebuild one Ollama embedding model:
    python3 scripts/rebuild_embeddings.py \\
      --database-url sqlite:///data/librarian.db \\
      --embedding-provider ollama \\
      --embedding-model all-minilm \\
      --reset

Clear all stored embeddings before benchmarking a different model:
    python3 scripts/rebuild_embeddings.py \\
      --database-url sqlite:///data/librarian.db \\
      --embedding-provider ollama \\
      --embedding-model nomic-embed-text \\
      --reset-all

Return machine-readable JSON for automation:
    python3 scripts/rebuild_embeddings.py \\
      --database-url sqlite:///data/librarian.db \\
      --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_config.config import (
    DATABASE_URL_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
)
from librarian_ingestion.embedding_ops import (
    RebuildEmbeddingsOptions,
    rebuild_embeddings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild chunk embeddings without deleting raw book text."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the ingestion database instead of {DATABASE_URL_ENV}.",
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
        "--batch-size",
        type=int,
        default=16,
        help="Number of chunks to send to the embedder per request.",
    )
    parser.add_argument(
        "--chunk-page-size",
        type=int,
        default=500,
        help="Number of stored chunks to read from the database at a time.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete embeddings for the selected provider/model before rebuilding.",
    )
    parser.add_argument(
        "--reset-all",
        action="store_true",
        help="Delete all embeddings before rebuilding the selected provider/model.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON for desktop apps and automation.",
    )
    args = parser.parse_args(argv)

    try:
        result = rebuild_embeddings(
            RebuildEmbeddingsOptions(
                database_url=args.database_url,
                embedding_provider=args.embedding_provider,
                embedding_model=args.embedding_model,
                ollama_base_url=args.ollama_base_url,
                batch_size=args.batch_size,
                chunk_page_size=args.chunk_page_size,
                reset=args.reset,
                reset_all=args.reset_all,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    print("Librarian embedding rebuild")
    print(f"Database: {result.database_url}")
    print(f"Embedding provider: {result.embedding_provider}")
    print(f"Embedding model: {result.embedding_model}")
    print(f"Chunks seen {result.chunks_seen}")
    print(f"Embeddings deleted {result.embeddings_deleted}")
    print(f"Embeddings stored {result.embeddings_stored}")
    print(f"Total embeddings {result.total_embeddings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
