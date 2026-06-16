from __future__ import annotations

from dataclasses import asdict, dataclass

from librarian_ingestion.config import (
    resolve_database_url,
    resolve_embedding_model,
    resolve_embedding_provider,
    resolve_ollama_base_url,
)
from librarian_ingestion.embeddings import create_embedder
from librarian_ingestion.storage import (
    EmbeddingRecord,
    StoredChunkRecord,
    create_ingestion_store,
)


@dataclass(frozen=True)
class RebuildEmbeddingsOptions:
    database_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    ollama_base_url: str | None = None
    batch_size: int = 16
    chunk_page_size: int = 500
    reset: bool = False
    reset_all: bool = False


@dataclass(frozen=True)
class RebuildEmbeddingsResult:
    database_url: str
    embedding_provider: str
    embedding_model: str
    chunks_seen: int
    embeddings_deleted: int
    embeddings_stored: int
    total_embeddings: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def rebuild_embeddings(
    options: RebuildEmbeddingsOptions | None = None,
) -> RebuildEmbeddingsResult:
    options = options or RebuildEmbeddingsOptions()
    database_url = resolve_database_url(options.database_url)
    provider = resolve_embedding_provider(options.embedding_provider)
    model = resolve_embedding_model(options.embedding_model)
    ollama_base_url = resolve_ollama_base_url(options.ollama_base_url)
    embedder = create_embedder(
        provider,
        model=model,
        ollama_base_url=ollama_base_url,
    )

    chunks_seen = 0
    embeddings_deleted = 0
    embeddings_stored = 0
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        if options.reset_all:
            embeddings_deleted = store.delete_chunk_embeddings()
        elif options.reset:
            embeddings_deleted = store.delete_chunk_embeddings(
                provider=embedder.provider,
                model=embedder.model,
            )

        offset = 0
        while True:
            chunks = store.list_chunks(limit=options.chunk_page_size, offset=offset)
            if not chunks:
                break
            offset += len(chunks)
            chunks_seen += len(chunks)
            records = _embed_stored_chunks(
                chunks,
                provider=embedder.provider,
                model=embedder.model,
                batch_size=options.batch_size,
                embed_texts=embedder.embed_texts,
            )
            store.save_chunk_embeddings(records)
            embeddings_stored += len(records)

        total_embeddings = store.count_embeddings()
    finally:
        store.close()

    return RebuildEmbeddingsResult(
        database_url=database_url,
        embedding_provider=embedder.provider,
        embedding_model=embedder.model,
        chunks_seen=chunks_seen,
        embeddings_deleted=embeddings_deleted,
        embeddings_stored=embeddings_stored,
        total_embeddings=total_embeddings,
    )


def _embed_stored_chunks(
    chunks: list[StoredChunkRecord],
    *,
    provider: str,
    model: str,
    batch_size: int,
    embed_texts,
) -> list[EmbeddingRecord]:
    records: list[EmbeddingRecord] = []
    safe_batch_size = max(1, batch_size)
    for start in range(0, len(chunks), safe_batch_size):
        batch = chunks[start:start + safe_batch_size]
        vectors = embed_texts([chunk.text for chunk in batch])
        if not vectors:
            continue
        if len(vectors) != len(batch):
            raise ValueError("embedder returned a different number of vectors")
        for chunk, vector in zip(batch, vectors):
            records.append(
                EmbeddingRecord(
                    id=f"{chunk.id}:{provider}:{model}",
                    chunk_id=chunk.id,
                    provider=provider,
                    model=model,
                    vector=vector,
                    dimensions=len(vector),
                )
            )
    return records
