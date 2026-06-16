#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
if str(INGESTION_PACKAGE) not in sys.path:
    sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.config import (
    BOOKS_DIR_ENV,
    DATABASE_URL_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
    resolve_database_url,
)
from librarian_ingestion.embedding_ops import (
    RebuildEmbeddingsOptions,
    rebuild_embeddings,
)
from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_ingestion.scan import EpubSourceError
from librarian_ingestion.storage import create_ingestion_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play with Librarian ingestion, chunks, embeddings, and DB state."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the ingestion database instead of {DATABASE_URL_ENV}.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    state_parser = subparsers.add_parser("state", help="Show database counts.")
    _add_json_flag(state_parser)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Scan EPUBs, parse text, chunk books, and store books/chunks.",
    )
    ingest_parser.add_argument(
        "--books-dir",
        help=f"Override the EPUB source directory instead of {BOOKS_DIR_ENV}.",
    )
    ingest_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-parse and store unchanged EPUB files.",
    )
    ingest_parser.add_argument(
        "--list",
        action="store_true",
        help="Include discovered EPUB files in the result.",
    )
    _add_json_flag(ingest_parser)

    embed_parser = subparsers.add_parser(
        "embed",
        help="Generate embeddings from stored chunks without deleting raw text.",
    )
    embed_parser.add_argument(
        "--embedding-provider",
        choices=["noop", "ollama"],
        help=f"Embedding provider override instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    embed_parser.add_argument(
        "--embedding-model",
        help=f"Embedding model override instead of {EMBEDDING_MODEL_ENV}.",
    )
    embed_parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )
    embed_parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Number of chunks to send to the embedder per request.",
    )
    embed_parser.add_argument(
        "--chunk-page-size",
        type=int,
        default=500,
        help="Number of stored chunks to read from the database at a time.",
    )
    embed_parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete embeddings for the selected provider/model before rebuilding.",
    )
    embed_parser.add_argument(
        "--reset-all",
        action="store_true",
        help="Delete all embeddings before rebuilding the selected provider/model.",
    )
    _add_json_flag(embed_parser)

    books_parser = subparsers.add_parser("books", help="Preview stored book rows.")
    books_parser.add_argument("--status", help="Filter by ingestion status.")
    _add_paging(books_parser, default_limit=20)
    _add_json_flag(books_parser)

    chunks_parser = subparsers.add_parser("chunks", help="Preview stored text chunks.")
    _add_paging(chunks_parser, default_limit=5)
    _add_json_flag(chunks_parser)

    embeddings_parser = subparsers.add_parser(
        "embeddings",
        help="Preview stored embedding rows and their linked chunk text.",
    )
    embeddings_parser.add_argument("--provider", help="Filter by provider.")
    embeddings_parser.add_argument("--model", help="Filter by model.")
    _add_paging(embeddings_parser, default_limit=5)
    _add_json_flag(embeddings_parser)

    args = parser.parse_args(argv)
    database_url = resolve_database_url(args.database_url)

    try:
        if args.command == "state":
            payload = _database_state(database_url)
            _print_payload(payload, args.json)
            return 0
        if args.command == "ingest":
            result = run_ingestion(
                IngestionOptions(
                    books_dir=args.books_dir,
                    database_url=database_url,
                    force=args.force,
                    list_epubs=args.list,
                )
            )
            _print_payload(result.to_dict(), args.json)
            return 0
        if args.command == "embed":
            result = rebuild_embeddings(
                RebuildEmbeddingsOptions(
                    database_url=database_url,
                    embedding_provider=args.embedding_provider,
                    embedding_model=args.embedding_model,
                    ollama_base_url=args.ollama_base_url,
                    batch_size=args.batch_size,
                    chunk_page_size=args.chunk_page_size,
                    reset=args.reset,
                    reset_all=args.reset_all,
                )
            )
            _print_payload(result.to_dict(), args.json)
            return 0
        if args.command == "books":
            payload = _list_books(
                database_url,
                status=args.status,
                limit=args.limit,
                offset=args.offset,
            )
            _print_payload(payload, args.json)
            return 0
        if args.command == "chunks":
            payload = _list_chunks(database_url, limit=args.limit, offset=args.offset)
            _print_payload(payload, args.json)
            return 0
        if args.command == "embeddings":
            payload = _list_embeddings(
                database_url,
                provider=args.provider,
                model=args.model,
                limit=args.limit,
                offset=args.offset,
            )
            _print_payload(payload, args.json)
            return 0
    except (EpubSourceError, ValueError, NotImplementedError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    parser.error(f"unsupported command: {args.command}")
    return 2


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )


def _add_paging(parser: argparse.ArgumentParser, *, default_limit: int) -> None:
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        help="Maximum rows to show.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Rows to skip.",
    )


def _database_state(database_url: str) -> dict[str, object]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        summary = asdict(store.get_summary())
        summary["embedding_models"] = [
            asdict(model_summary)
            for model_summary in store.get_embedding_model_summaries()
        ]
        return summary
    finally:
        store.close()


def _list_books(
    database_url: str,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return [
            asdict(book)
            for book in store.list_books(status=status, limit=limit, offset=offset)
        ]
    finally:
        store.close()


def _list_chunks(
    database_url: str,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return [
            asdict(chunk)
            for chunk in store.list_chunks(limit=limit, offset=offset)
        ]
    finally:
        store.close()


def _list_embeddings(
    database_url: str,
    *,
    provider: str | None,
    model: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        return [
            asdict(embedding)
            for embedding in store.list_embeddings(
                provider=provider,
                model=model,
                limit=limit,
                offset=offset,
            )
        ]
    finally:
        store.close()


def _print_payload(payload: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    if isinstance(payload, dict):
        _print_dict(payload)
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                _print_dict(item)
                print()
            else:
                print(item)
        return
    print(payload)


def _print_dict(payload: dict[str, object]) -> None:
    for key, value in payload.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
