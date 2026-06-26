from __future__ import annotations

from dataclasses import dataclass

from librarian_config.config import resolve_opensearch_index, resolve_opensearch_url
from librarian_ingestion.embedding_ops import EmbedQueryOptions, embed_query
from librarian_search.opensearch import OpenSearchClient
from librarian_search.search import SearchResponse, SearchResult


@dataclass(frozen=True)
class HybridSearchOptions:
    query: str
    opensearch_url: str | None = None
    index_name: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    ollama_base_url: str | None = None
    limit: int = 10
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    genre: str | None = None
    tag: str | None = None


def hybrid_search_chunks(options: HybridSearchOptions) -> SearchResponse:
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
            filters=_hybrid_filters(options),
            results=[],
        )

    client = OpenSearchClient(resolve_opensearch_url(options.opensearch_url))
    hits = client.search_hybrid(
        resolve_opensearch_index(options.index_name),
        query=query_embedding.query,
        vector=query_embedding.vector,
        provider=query_embedding.embedding_provider,
        model=query_embedding.embedding_model,
        limit=max(1, options.limit),
        book_id=_clean_filter(options.book_id),
        book_title=_clean_filter(options.book_title),
        author=_clean_filter(options.author),
        genre=_clean_filter(options.genre),
        tag=_clean_filter(options.tag),
    )

    return SearchResponse(
        query=query_embedding.query,
        embedding_provider=query_embedding.embedding_provider,
        embedding_model=query_embedding.embedding_model,
        dimensions=query_embedding.dimensions,
        candidate_count=len(hits),
        filters=_hybrid_filters(options),
        results=[_result_from_hit(hit) for hit in hits],
    )


def _result_from_hit(hit) -> SearchResult:
    document = hit.document
    return SearchResult(
        score=hit.score,
        chunk_id=document.chunk_id,
        book_id=document.book_id,
        relative_path=document.relative_path,
        title=document.title,
        authors=document.authors,
        publisher=document.publisher,
        chunk_index=document.chunk_index,
        text=document.text,
        embedding_provider=document.embedding_provider,
        embedding_model=document.embedding_model,
        dimensions=document.dimensions,
    )


def _hybrid_filters(options: HybridSearchOptions) -> dict[str, str]:
    filters = {
        "book_id": _clean_filter(options.book_id),
        "book_title": _clean_filter(options.book_title),
        "author": _clean_filter(options.author),
        "genre": _clean_filter(options.genre),
        "tag": _clean_filter(options.tag),
    }
    return {key: value for key, value in filters.items() if value}


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
