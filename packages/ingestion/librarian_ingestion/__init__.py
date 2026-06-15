from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from librarian_ingestion.chunk import TextChunk
    from librarian_ingestion.embeddings import Embedder, EmbeddingError
    from librarian_ingestion.epub import ParsedBook
    from librarian_ingestion.ingest import IngestionOptions, IngestionResult
    from librarian_ingestion.scan import DiscoveredEpub, EpubSourceError
    from librarian_ingestion.storage import (
        BookRecord,
        ChunkRecord,
        EmbeddingRecord,
        IngestionStore,
        IngestionSummary,
        StoredBookRecord,
    )

__all__ = [
    "BookRecord",
    "ChunkRecord",
    "DiscoveredEpub",
    "Embedder",
    "EmbeddingError",
    "EmbeddingRecord",
    "EpubSourceError",
    "IngestionStore",
    "IngestionOptions",
    "IngestionResult",
    "IngestionSummary",
    "ParsedBook",
    "StoredBookRecord",
    "TextChunk",
    "chunk_text",
    "clean_text",
    "create_embedder",
    "create_ingestion_store",
    "parse_epub",
    "run_ingestion",
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

    if name in {"Embedder", "EmbeddingError", "create_embedder"}:
        from librarian_ingestion.embeddings import (
            Embedder,
            EmbeddingError,
            create_embedder,
        )

        return {
            "Embedder": Embedder,
            "EmbeddingError": EmbeddingError,
            "create_embedder": create_embedder,
        }[name]

    if name in {
        "BookRecord",
        "ChunkRecord",
        "EmbeddingRecord",
        "IngestionStore",
        "IngestionSummary",
        "StoredBookRecord",
        "create_ingestion_store",
    }:
        from librarian_ingestion.storage import (
            BookRecord,
            ChunkRecord,
            EmbeddingRecord,
            IngestionStore,
            IngestionSummary,
            StoredBookRecord,
            create_ingestion_store,
        )

        return {
            "BookRecord": BookRecord,
            "ChunkRecord": ChunkRecord,
            "EmbeddingRecord": EmbeddingRecord,
            "IngestionStore": IngestionStore,
            "IngestionSummary": IngestionSummary,
            "StoredBookRecord": StoredBookRecord,
            "create_ingestion_store": create_ingestion_store,
        }[name]

    if name in {"IngestionOptions", "IngestionResult", "run_ingestion"}:
        from librarian_ingestion.ingest import (
            IngestionOptions,
            IngestionResult,
            run_ingestion,
        )

        return {
            "IngestionOptions": IngestionOptions,
            "IngestionResult": IngestionResult,
            "run_ingestion": run_ingestion,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
