#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
if str(INGESTION_PACKAGE) not in sys.path:
    sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.config import BOOKS_DIR_ENV, resolve_books_dir
from librarian_ingestion.scan import EpubSourceError, scan_epub_files


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
    args = parser.parse_args(argv)

    books_dir = resolve_books_dir(args.books_dir)

    print("Librarian EPUB ingestion")
    print(f"Books directory: {books_dir}")

    try:
        epubs = scan_epub_files(books_dir)
    except EpubSourceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(f"Found {len(epubs)} EPUB files")

    if args.list:
        for epub in epubs:
            print(
                f"- {epub.relative_path} "
                f"({epub.size_bytes} bytes, sha256={epub.sha256})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
