from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from librarian_ingestion.chunk import TextChunk
    from librarian_ingestion.embedding_ops import (
        EmbedQueryOptions,
        EmbedQueryResult,
        RebuildEmbeddingsOptions,
        RebuildEmbeddingsResult,
    )
    from librarian_ingestion.embeddings import Embedder, EmbeddingError
    from librarian_ingestion.epub import ParsedBook
    from librarian_ingestion.ingest import IngestionOptions, IngestionResult
    from librarian_ingestion.scan import DiscoveredEpub, EpubSourceError
    from librarian_ingestion.storage import (
        BookRecord,
        ChunkRecord,
        EmbeddingModelSummary,
        EmbeddingRecord,
        IngestionStore,
        IngestionSummary,
        StoredBookRecord,
        StoredEmbeddingRecord,
    )

__all__ = [
    "BookRecord",
    "ChunkRecord",
    "DiscoveredEpub",
    "Embedder",
    "EmbeddingError",
    "EmbeddingModelSummary",
    "EmbeddingRecord",
    "EmbedQueryOptions",
    "EmbedQueryResult",
    "EpubSourceError",
    "IngestionStore",
    "IngestionOptions",
    "IngestionResult",
    "IngestionSummary",
    "ParsedBook",
    "RebuildEmbeddingsOptions",
    "RebuildEmbeddingsResult",
    "StoredBookRecord",
    "StoredEmbeddingRecord",
    "TextChunk",
    "chunk_text",
    "clean_text",
    "create_configured_embedder",
    "create_embedder",
    "create_ingestion_store",
    "embed_query",
    "parse_epub",
    "rebuild_embeddings",
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

    if name in {
        "Embedder",
        "EmbeddingError",
        "create_configured_embedder",
        "create_embedder",
    }:
        from librarian_ingestion.embeddings import (
            Embedder,
            EmbeddingError,
            create_configured_embedder,
            create_embedder,
        )

        return {
            "Embedder": Embedder,
            "EmbeddingError": EmbeddingError,
            "create_configured_embedder": create_configured_embedder,
            "create_embedder": create_embedder,
        }[name]

    if name in {
        "RebuildEmbeddingsOptions",
        "RebuildEmbeddingsResult",
        "EmbedQueryOptions",
        "EmbedQueryResult",
        "embed_query",
        "rebuild_embeddings",
    }:
        from librarian_ingestion.embedding_ops import (
            EmbedQueryOptions,
            EmbedQueryResult,
            RebuildEmbeddingsOptions,
            RebuildEmbeddingsResult,
            embed_query,
            rebuild_embeddings,
        )

        return {
            "EmbedQueryOptions": EmbedQueryOptions,
            "EmbedQueryResult": EmbedQueryResult,
            "RebuildEmbeddingsOptions": RebuildEmbeddingsOptions,
            "RebuildEmbeddingsResult": RebuildEmbeddingsResult,
            "embed_query": embed_query,
            "rebuild_embeddings": rebuild_embeddings,
        }[name]

    if name in {
        "BookRecord",
        "ChunkRecord",
        "EmbeddingModelSummary",
        "EmbeddingRecord",
        "IngestionStore",
        "IngestionSummary",
        "StoredBookRecord",
        "StoredEmbeddingRecord",
        "create_ingestion_store",
    }:
        from librarian_ingestion.storage import (
            BookRecord,
            ChunkRecord,
            EmbeddingModelSummary,
            EmbeddingRecord,
            IngestionStore,
            IngestionSummary,
            StoredBookRecord,
            StoredEmbeddingRecord,
            create_ingestion_store,
        )

        return {
            "BookRecord": BookRecord,
            "ChunkRecord": ChunkRecord,
            "EmbeddingModelSummary": EmbeddingModelSummary,
            "EmbeddingRecord": EmbeddingRecord,
            "IngestionStore": IngestionStore,
            "IngestionSummary": IngestionSummary,
            "StoredBookRecord": StoredBookRecord,
            "StoredEmbeddingRecord": StoredEmbeddingRecord,
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
