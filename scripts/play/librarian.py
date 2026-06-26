#!/usr/bin/env python3
"""Developer playground CLI for inspecting Librarian's local pipeline.

This script is intentionally human/operator-facing: it exposes step-by-step
commands for ingesting EPUBs, previewing books/chunks, rebuilding embeddings,
running local search, and inspecting database state. Product code should call
the package services or FastAPI endpoints rather than shelling out to this
script.

Use this when you want a tactile view of the local pipeline while building or
debugging: ingest, inspect database counts, list books/chunks/embeddings, rebuild
vectors, and run retrieval searches from one CLI.

Examples:

Show database state:
    python3 scripts/play/librarian.py \\
      --database-url sqlite:///data/librarian.db \\
      state

Ingest EPUBs from a local source directory:
    python3 scripts/play/librarian.py \\
      --database-url sqlite:///data/librarian.db \\
      ingest \\
      --books-dir ./Epub-Books

Ingest EPUBs and queue asynchronous summary jobs:
    python3 scripts/play/librarian.py \\
      --database-url sqlite:///data/librarian.db \\
      ingest \\
      --books-dir ./Epub-Books \\
      --enqueue-summaries \\
      --summary-generation-provider codex \\
      --summary-generation-model codex

Rebuild embeddings after changing the embedding model:
    python3 scripts/play/librarian.py \\
      --database-url sqlite:///data/librarian.db \\
      embed \\
      --embedding-provider ollama \\
      --embedding-model all-minilm \\
      --reset

Search within one author or book:
    python3 scripts/play/librarian.py \\
      --database-url sqlite:///data/librarian.db \\
      search "How brutal and terrible is war?" \\
      --author "Erich Maria Remarque" \\
      --limit 10

Run OpenSearch-backed hybrid retrieval after indexing chunks:
    python3 scripts/play/librarian.py \\
      hybrid-search "psychohistory and empire" \\
      --opensearch-url http://localhost:9200 \\
      --embedding-provider ollama \\
      --embedding-model all-minilm \\
      --genre "Science Fiction"

Ask for book-level recommendations using retrieval plus generated metadata:
    python3 scripts/play/librarian.py \\
      --database-url sqlite:///data/librarian.db \\
      recommend "I want a thoughtful science fiction book" \\
      --genre "Science Fiction" \\
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
    BOOKS_DIR_ENV,
    DATABASE_URL_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_PROVIDER_ENV,
    GENERATION_MODEL_ENV,
    GENERATION_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
    resolve_database_url,
)
from librarian_ingestion.embedding_ops import (
    RebuildEmbeddingsOptions,
    rebuild_embeddings,
)
from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_ingestion.scan import EpubSourceError
from librarian_logging import configure_cli_logging, emit_json
from librarian_recommendations.recommendations import (
    RecommendationOptions,
    recommend_books,
)
from librarian_search.hybrid import HybridSearchOptions, hybrid_search_chunks
from librarian_search.search import SearchOptions, search_chunks
from librarian_storage.storage import create_ingestion_store

logger = logging.getLogger(__name__)


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
    ingest_parser.add_argument(
        "--enqueue-summaries",
        action="store_true",
        help="Queue asynchronous chapter/book summary jobs for newly ingested books.",
    )
    ingest_parser.add_argument(
        "--summary-generation-provider",
        choices=["noop", "ollama", "codex"],
        help=f"Summary provider override instead of {GENERATION_PROVIDER_ENV}.",
    )
    ingest_parser.add_argument(
        "--summary-generation-model",
        help=f"Summary model override instead of {GENERATION_MODEL_ENV}.",
    )
    ingest_parser.add_argument(
        "--summary-detail",
        choices=["short", "medium", "detailed"],
        default="medium",
        help="Queued summary detail level.",
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

    search_parser = subparsers.add_parser(
        "search",
        help="Embed a query and rank stored chunks by cosine similarity.",
    )
    search_parser.add_argument("query", help="Natural-language search query.")
    search_parser.add_argument(
        "--embedding-provider",
        choices=["noop", "ollama"],
        help=f"Embedding provider override instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    search_parser.add_argument(
        "--embedding-model",
        help=f"Embedding model override instead of {EMBEDDING_MODEL_ENV}.",
    )
    search_parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum ranked chunks to show.",
    )
    search_parser.add_argument("--book-id", help="Restrict search to one stored book id.")
    search_parser.add_argument(
        "--book-title",
        help="Restrict search to matching book titles.",
    )
    search_parser.add_argument("--author", help="Restrict search to matching author names.")
    _add_json_flag(search_parser)

    hybrid_parser = subparsers.add_parser(
        "hybrid-search",
        help="Search chunks through OpenSearch keyword plus vector retrieval.",
    )
    hybrid_parser.add_argument("query", help="Natural-language search query.")
    hybrid_parser.add_argument("--opensearch-url", help="OpenSearch URL override.")
    hybrid_parser.add_argument("--index-name", help="OpenSearch index override.")
    hybrid_parser.add_argument(
        "--embedding-provider",
        choices=["noop", "ollama"],
        help=f"Embedding provider override instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    hybrid_parser.add_argument(
        "--embedding-model",
        help=f"Embedding model override instead of {EMBEDDING_MODEL_ENV}.",
    )
    hybrid_parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )
    hybrid_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum ranked chunks to show.",
    )
    hybrid_parser.add_argument("--book-id", help="Restrict search to one stored book id.")
    hybrid_parser.add_argument(
        "--book-title",
        help="Restrict search to matching book titles.",
    )
    hybrid_parser.add_argument("--author", help="Restrict search to matching author names.")
    hybrid_parser.add_argument("--genre", help="Restrict search to a generated genre.")
    hybrid_parser.add_argument("--tag", help="Restrict search to a generated topic tag.")
    _add_json_flag(hybrid_parser)

    recommend_parser = subparsers.add_parser(
        "recommend",
        help="Recommend books by aggregating retrieved chunks and book metadata.",
    )
    recommend_parser.add_argument("query", help="Natural-language recommendation request.")
    recommend_parser.add_argument(
        "--embedding-provider",
        choices=["noop", "ollama"],
        help=f"Embedding provider override instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    recommend_parser.add_argument(
        "--embedding-model",
        help=f"Embedding model override instead of {EMBEDDING_MODEL_ENV}.",
    )
    recommend_parser.add_argument(
        "--generation-provider",
        choices=["noop", "ollama", "codex"],
        help=f"Generation provider override instead of {GENERATION_PROVIDER_ENV}.",
    )
    recommend_parser.add_argument(
        "--generation-model",
        help=f"Generation model override instead of {GENERATION_MODEL_ENV}.",
    )
    recommend_parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )
    recommend_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum books to recommend.",
    )
    recommend_parser.add_argument(
        "--retrieval-limit",
        type=int,
        default=40,
        help="Maximum retrieved chunks to aggregate into book recommendations.",
    )
    recommend_parser.add_argument("--book-id", help="Restrict to one stored book id.")
    recommend_parser.add_argument(
        "--book-title",
        help="Restrict to matching book titles.",
    )
    recommend_parser.add_argument("--author", help="Restrict to matching author names.")
    recommend_parser.add_argument(
        "--genre",
        help="Require a stored generated genre containing this text.",
    )
    recommend_parser.add_argument(
        "--tag",
        help="Require a stored generated topic tag containing this text.",
    )
    _add_json_flag(recommend_parser)

    args = parser.parse_args(argv)
    configure_cli_logging(console=not getattr(args, "json", False))
    database_url = resolve_database_url(args.database_url)

    try:
        if args.command == "state":
            payload = _database_state(database_url)
            _log_payload(payload, args.json)
            return 0
        if args.command == "ingest":
            result = run_ingestion(
                IngestionOptions(
                    books_dir=_resolve_play_books_dir(args.books_dir),
                    database_url=database_url,
                    force=args.force,
                    list_epubs=args.list,
                    enqueue_summaries=args.enqueue_summaries,
                    summary_generation_provider=args.summary_generation_provider,
                    summary_generation_model=args.summary_generation_model,
                    summary_detail=args.summary_detail,
                )
            )
            _log_payload(result.to_dict(), args.json)
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
            _log_payload(result.to_dict(), args.json)
            return 0
        if args.command == "books":
            payload = _list_books(
                database_url,
                status=args.status,
                limit=args.limit,
                offset=args.offset,
            )
            _log_payload(payload, args.json)
            return 0
        if args.command == "chunks":
            payload = _list_chunks(database_url, limit=args.limit, offset=args.offset)
            _log_payload(payload, args.json)
            return 0
        if args.command == "embeddings":
            payload = _list_embeddings(
                database_url,
                provider=args.provider,
                model=args.model,
                limit=args.limit,
                offset=args.offset,
            )
            _log_payload(payload, args.json)
            return 0
        if args.command == "search":
            result = search_chunks(
                SearchOptions(
                    query=args.query,
                    database_url=database_url,
                    embedding_provider=args.embedding_provider,
                    embedding_model=args.embedding_model,
                    ollama_base_url=args.ollama_base_url,
                    limit=args.limit,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                )
            )
            payload = result.to_dict()
            if args.json:
                _log_payload(payload, args.json)
            else:
                _log_search_response(payload)
            return 0
        if args.command == "hybrid-search":
            result = hybrid_search_chunks(
                HybridSearchOptions(
                    query=args.query,
                    opensearch_url=args.opensearch_url,
                    index_name=args.index_name,
                    embedding_provider=args.embedding_provider,
                    embedding_model=args.embedding_model,
                    ollama_base_url=args.ollama_base_url,
                    limit=args.limit,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    genre=args.genre,
                    tag=args.tag,
                )
            )
            payload = result.to_dict()
            if args.json:
                _log_payload(payload, args.json)
            else:
                _log_search_response(payload)
            return 0
        if args.command == "recommend":
            result = recommend_books(
                RecommendationOptions(
                    query=args.query,
                    database_url=database_url,
                    embedding_provider=args.embedding_provider,
                    embedding_model=args.embedding_model,
                    generation_provider=args.generation_provider,
                    generation_model=args.generation_model,
                    ollama_base_url=args.ollama_base_url,
                    limit=args.limit,
                    retrieval_limit=args.retrieval_limit,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    genre=args.genre,
                    tag=args.tag,
                )
            )
            payload = result.to_dict()
            if args.json:
                _log_payload(payload, args.json)
            else:
                _log_recommendation_response(payload)
            return 0
    except (EpubSourceError, ValueError, NotImplementedError, RuntimeError) as error:
        logger.error("Error: %s", error)
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


def _resolve_play_books_dir(books_dir: str | None) -> str | None:
    if not books_dir:
        return None

    path = Path(books_dir).expanduser()
    if path.is_absolute() or path.exists():
        return str(path)

    repo_relative = REPO_ROOT / path
    if repo_relative.exists():
        return str(repo_relative)

    return str(path)


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


def _log_payload(payload: object, as_json: bool) -> None:
    if as_json:
        emit_json(payload)
        return

    if isinstance(payload, dict):
        _log_dict(payload)
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                _log_dict(item, trailing_newline=True)
            else:
                logger.info("%s", item)
        return
    logger.info("%s", payload)


def _log_dict(payload: dict[str, object], *, trailing_newline: bool = False) -> None:
    last_key = next(reversed(payload), None)
    for key, value in payload.items():
        suffix = "\n" if trailing_newline and key == last_key else ""
        logger.info("%s: %s%s", key, value, suffix)


def _log_search_response(payload: dict[str, object]) -> None:
    logger.info("Librarian search")
    logger.info("Query: %s", payload["query"])
    logger.info(
        "Embedding: "
        f"{payload['embedding_provider']} / {payload['embedding_model']} "
        f"({payload['dimensions']} dimensions)"
    )
    logger.info("Candidates scored: %s", payload["candidate_count"])
    filters = payload.get("filters")
    if isinstance(filters, dict) and filters:
        logger.info("Filters: %s", filters)

    results = payload["results"]
    if not isinstance(results, list) or not results:
        logger.info("No matching chunks found.")
        return

    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        title = result["title"] or result["relative_path"]
        authors = result["authors"]
        author_text = ", ".join(authors) if isinstance(authors, list) else authors
        logger.info("%s. score=%.4f", index, float(result["score"]))
        logger.info("\tbook: %s", title)
        if author_text:
            logger.info("\tauthors: %s", author_text)
        logger.info(
            "\tsource: %s chunk %s",
            result["relative_path"],
            result["chunk_index"],
        )
        logger.info(
            "\ttext: %s\n",
            _single_line(str(result["text"]), max_length=360),
        )


def _log_recommendation_response(payload: dict[str, object]) -> None:
    logger.info("Librarian recommendations")
    logger.info("Query: %s", payload["query"])
    logger.info("Answer:")
    logger.info("%s", payload["answer"])
    logger.info(
        "\nModels: "
        f"embedding={payload['embedding_provider']}/{payload['embedding_model']}, "
        f"generation={payload['generation_provider']}/{payload['generation_model']}"
    )
    logger.info("Book candidates: %s", payload["candidate_count"])
    filters = payload.get("filters")
    if isinstance(filters, dict) and filters:
        logger.info("Filters: %s", filters)

    recommendations = payload["recommendations"]
    if not isinstance(recommendations, list) or not recommendations:
        logger.info("No matching books found.")
        return

    for item in recommendations:
        if not isinstance(item, dict):
            continue
        title = item["title"] or item["relative_path"]
        authors = item["authors"]
        author_text = ", ".join(authors) if isinstance(authors, list) else authors
        logger.info(
            "#%s score=%.4f %s",
            item["rank"],
            float(item["score"]),
            title,
        )
        if author_text:
            logger.info("\tauthors: %s", author_text)
        if item.get("genres"):
            logger.info("\tgenres: %s", ", ".join(str(value) for value in item["genres"]))
        if item.get("tags"):
            logger.info("\ttags: %s", ", ".join(str(value) for value in item["tags"]))
        evidence = item.get("evidence")
        if isinstance(evidence, list):
            for source in evidence[:2]:
                if isinstance(source, dict):
                    logger.info(
                        "\t[%s] %s",
                        source["source_id"],
                        _single_line(str(source["text"]), max_length=240),
                    )


def _single_line(text: str, *, max_length: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3]}..."


if __name__ == "__main__":
    raise SystemExit(main())
