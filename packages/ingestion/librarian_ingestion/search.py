from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from librarian_ingestion.embedding_ops import EmbedQueryOptions, embed_query
from librarian_ingestion.config import resolve_database_url
from librarian_ingestion.storage import SearchEmbeddingRecord, create_ingestion_store


@dataclass(frozen=True)
class SearchOptions:
    query: str
    database_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    ollama_base_url: str | None = None
    limit: int = 10


@dataclass(frozen=True)
class SearchResult:
    score: float
    chunk_id: str
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    publisher: str | None
    chunk_index: int
    text: str
    embedding_provider: str
    embedding_model: str
    dimensions: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResponse:
    query: str
    embedding_provider: str
    embedding_model: str
    dimensions: int
    candidate_count: int
    results: list[SearchResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "dimensions": self.dimensions,
            "candidate_count": self.candidate_count,
            "results": [result.to_dict() for result in self.results],
        }


def search_chunks(options: SearchOptions) -> SearchResponse:
    query_embedding = embed_query(
        EmbedQueryOptions(
            query=options.query,
            embedding_provider=options.embedding_provider,
            embedding_model=options.embedding_model,
            ollama_base_url=options.ollama_base_url,
        )
    )
    if not query_embedding.vector:
        return SearchResponse(
            query=query_embedding.query,
            embedding_provider=query_embedding.embedding_provider,
            embedding_model=query_embedding.embedding_model,
            dimensions=query_embedding.dimensions,
            candidate_count=0,
            results=[],
        )

    database_url = resolve_database_url(options.database_url)
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        # The query vector can only be compared to chunk vectors from the same
        # provider/model; otherwise cosine scores are meaningless.
        candidates = store.list_search_embeddings(
            provider=query_embedding.embedding_provider,
            model=query_embedding.embedding_model,
        )
    finally:
        store.close()

    scored = _score_candidates(query_embedding.vector, candidates)
    limit = max(1, options.limit)
    return SearchResponse(
        query=query_embedding.query,
        embedding_provider=query_embedding.embedding_provider,
        embedding_model=query_embedding.embedding_model,
        dimensions=query_embedding.dimensions,
        candidate_count=len(scored),
        results=scored[:limit],
    )


def _score_candidates(
    query_vector: list[float],
    candidates: list[SearchEmbeddingRecord],
) -> list[SearchResult]:
    compatible = [
        candidate
        for candidate in candidates
        if candidate.dimensions == len(query_vector)
        and len(candidate.vector) == len(query_vector)
    ]
    if not compatible:
        return []

    matrix = np.asarray([candidate.vector for candidate in compatible], dtype=np.float32)
    query = np.asarray(query_vector, dtype=np.float32)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return []

    denominators = matrix_norms * query_norm
    nonzero = denominators > 0
    if not np.any(nonzero):
        return []

    scores = np.full(len(compatible), -1.0, dtype=np.float32)
    scores[nonzero] = (matrix[nonzero] @ query) / denominators[nonzero]
    order = np.argsort(scores)[::-1]

    results: list[SearchResult] = []
    for index in order:
        score = float(scores[index])
        if score < -0.999999:
            continue
        candidate = compatible[int(index)]
        results.append(
            SearchResult(
                score=score,
                chunk_id=candidate.chunk_id,
                book_id=candidate.book_id,
                relative_path=candidate.relative_path,
                title=candidate.title,
                authors=candidate.authors,
                publisher=candidate.publisher,
                chunk_index=candidate.chunk_index,
                text=candidate.text,
                embedding_provider=candidate.provider,
                embedding_model=candidate.model,
                dimensions=candidate.dimensions,
            )
        )
    return results
