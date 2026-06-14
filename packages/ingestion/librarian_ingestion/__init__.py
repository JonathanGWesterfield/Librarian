from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from librarian_ingestion.chunk import TextChunk
    from librarian_ingestion.epub import ParsedBook
    from librarian_ingestion.scan import DiscoveredEpub, EpubSourceError
    from librarian_ingestion.storage import BookRecord, ChunkRecord, IngestionStore

__all__ = [
    "BookRecord",
    "ChunkRecord",
    "DiscoveredEpub",
    "EpubSourceError",
    "IngestionStore",
    "ParsedBook",
    "TextChunk",
    "chunk_text",
    "clean_text",
    "create_ingestion_store",
    "parse_epub",
    "scan_epub_files",
]


def __getattr__(name: str):
    if name in {"ParsedBook", "parse_epub"}:
        from librarian_ingestion.epub import ParsedBook, parse_epub

        return {"ParsedBook": ParsedBook, "parse_epub": parse_epub}[name]

    if name in {"DiscoveredEpub", "EpubSourceError", "scan_epub_files"}:
        from librarian_ingestion.scan import (
            DiscoveredEpub,
            EpubSourceError,
            scan_epub_files,
        )

        return {
            "DiscoveredEpub": DiscoveredEpub,
            "EpubSourceError": EpubSourceError,
            "scan_epub_files": scan_epub_files,
        }[name]

    if name in {"TextChunk", "chunk_text", "clean_text"}:
        from librarian_ingestion.chunk import TextChunk, chunk_text, clean_text

        return {
            "TextChunk": TextChunk,
            "chunk_text": chunk_text,
            "clean_text": clean_text,
        }[name]

    if name in {"BookRecord", "ChunkRecord", "IngestionStore", "create_ingestion_store"}:
        from librarian_ingestion.storage import (
            BookRecord,
            ChunkRecord,
            IngestionStore,
            create_ingestion_store,
        )

        return {
            "BookRecord": BookRecord,
            "ChunkRecord": ChunkRecord,
            "IngestionStore": IngestionStore,
            "create_ingestion_store": create_ingestion_store,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
