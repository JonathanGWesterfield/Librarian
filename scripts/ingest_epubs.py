#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
if str(INGESTION_PACKAGE) not in sys.path:
    sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.chunk import chunk_text
from librarian_ingestion.config import (
    BOOKS_DIR_ENV,
    DATABASE_URL_ENV,
    resolve_books_dir,
    resolve_database_url,
)
from librarian_ingestion.epub import parse_epub
from librarian_ingestion.scan import EpubSourceError, scan_epub_files
from librarian_ingestion.storage import (
    BookRecord,
    ChunkRecord,
    create_ingestion_store,
    utc_now,
)


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
    args = parser.parse_args(argv)

    books_dir = resolve_books_dir(args.books_dir)
    database_url = resolve_database_url(args.database_url)

    print("Librarian EPUB ingestion")
    print(f"Books directory: {books_dir}")
    print(f"Database: {database_url}")

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

    parsed_count = 0
    skipped_count = 0
    failed_count = 0
    chunk_count = 0

    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        for discovered in epubs:
            existing = store.get_book_by_relative_path(discovered.relative_path)
            if (
                existing
                and existing.file_hash == discovered.sha256
                and existing.status == "ingested"
                and not args.force
            ):
                skipped_count += 1
                continue

            try:
                parsed = parse_epub(discovered.path)
                chunks = chunk_text(parsed.text)
                book = BookRecord(
                    id=discovered.sha256,
                    source_path=str(discovered.path),
                    relative_path=discovered.relative_path,
                    file_hash=discovered.sha256,
                    size_bytes=discovered.size_bytes,
                    title=parsed.title,
                    authors=parsed.authors,
                    status="ingested",
                    ingested_at=utc_now(),
                )
                chunk_records = [
                    ChunkRecord(
                        id=f"{discovered.sha256}:{chunk.chunk_index}",
                        book_id=discovered.sha256,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        character_count=chunk.character_count,
                        token_estimate=chunk.token_estimate,
                    )
                    for chunk in chunks
                ]
                store.save_book_with_chunks(book, chunk_records)
                parsed_count += 1
                chunk_count += len(chunk_records)
            except Exception as error:
                failed_count += 1
                failed_book = BookRecord(
                    id=discovered.sha256,
                    source_path=str(discovered.path),
                    relative_path=discovered.relative_path,
                    file_hash=discovered.sha256,
                    size_bytes=discovered.size_bytes,
                    title=None,
                    authors=[],
                    status="failed",
                    error_message=str(error),
                )
                store.save_book_with_chunks(failed_book, [])
                print(f"Failed {discovered.relative_path}: {error}", file=sys.stderr)

        total_books = store.count_books()
        total_chunks = store.count_chunks()
    finally:
        store.close()

    print(f"Parsed {parsed_count}")
    print(f"Skipped unchanged {skipped_count}")
    print(f"Failed {failed_count}")
    print(f"Stored chunks {chunk_count}")
    print(f"Database totals: {total_books} books, {total_chunks} chunks")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
