#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
if str(INGESTION_PACKAGE) not in sys.path:
    sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.config import (
    BOOKS_DIR_ENV,
    DATABASE_URL_ENV,
)
from librarian_ingestion.ingest import IngestionOptions, run_ingestion
from librarian_ingestion.scan import EpubSourceError


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    try:
        result = run_ingestion(
            IngestionOptions(
                books_dir=args.books_dir,
                database_url=args.database_url,
                force=args.force,
                list_epubs=args.list,
            )
        )
    except (EpubSourceError, ValueError, NotImplementedError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    print("Librarian EPUB ingestion")
    print(f"Books directory: {result.books_dir}")
    print(f"Database: {result.database_url}")
    print(f"Found {result.found} EPUB files")

    if args.list:
        for epub in result.discovered:
            print(
                f"- {epub['relative_path']} "
                f"({epub['size_bytes']} bytes, sha256={epub['sha256']})"
            )

    for book in result.books:
        if book.status == "failed":
            print(f"Failed {book.relative_path}: {book.message}", file=sys.stderr)

    print(f"Parsed {result.parsed}")
    print(f"Skipped unchanged {result.skipped_unchanged}")
    print(f"Skipped duplicates {result.skipped_duplicates}")
    print(f"Failed {result.failed}")
    print(f"Stored chunks {result.stored_chunks}")
    print(f"Database totals: {result.total_books} books, {result.total_chunks} chunks")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
