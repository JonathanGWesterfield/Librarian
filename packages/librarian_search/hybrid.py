from __future__ import annotations

import re
from dataclasses import dataclass

from librarian_config.config import resolve_opensearch_index, resolve_opensearch_url
from librarian_ingestion.embedding_ops import EmbedQueryOptions, embed_query
from librarian_search.opensearch import OpenSearchClient, OpenSearchHit
from librarian_search.search import SearchResponse, SearchResult

DEFAULT_RERANK_CANDIDATE_MULTIPLIER = 4


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
    rerank_candidate_multiplier: int = DEFAULT_RERANK_CANDIDATE_MULTIPLIER


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
    result_limit = max(1, options.limit)
    candidate_limit = result_limit * max(1, options.rerank_candidate_multiplier)
    hits = client.search_hybrid(
        resolve_opensearch_index(options.index_name),
        query=query_embedding.query,
        vector=query_embedding.vector,
        provider=query_embedding.embedding_provider,
        model=query_embedding.embedding_model,
        limit=candidate_limit,
        book_id=_clean_filter(options.book_id),
        book_title=_clean_filter(options.book_title),
        author=_clean_filter(options.author),
        genre=_clean_filter(options.genre),
        tag=_clean_filter(options.tag),
    )
    reranked_hits = _rerank_hits(query_embedding.query, hits, limit=result_limit)

    return SearchResponse(
        query=query_embedding.query,
        embedding_provider=query_embedding.embedding_provider,
        embedding_model=query_embedding.embedding_model,
        dimensions=query_embedding.dimensions,
        candidate_count=len(hits),
        filters=_hybrid_filters(options),
        results=[_result_from_hit(hit) for hit in reranked_hits],
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


def _rerank_hits(query: str, hits: list[OpenSearchHit], *, limit: int) -> list[OpenSearchHit]:
    if not hits:
        return []

    query_phrase = _normalize_text(query)
    query_terms = _query_terms(query)
    reranked: list[OpenSearchHit] = []
    for hit in hits:
        boost = _metadata_boost(query_phrase, query_terms, hit)
        reranked.append(OpenSearchHit(score=hit.score + boost, document=hit.document))
    reranked.sort(key=lambda hit: hit.score, reverse=True)
    return reranked[: max(1, limit)]


def _metadata_boost(
    query_phrase: str,
    query_terms: set[str],
    hit: OpenSearchHit,
) -> float:
    document = hit.document
    text = _normalize_text(document.text)
    title = _normalize_text(document.title or "")
    authors = _normalize_text(" ".join(document.authors))
    tags = _normalize_text(" ".join(document.tags))
    genres = _normalize_text(" ".join(document.genres))
    searchable = " ".join([text, title, authors, tags, genres])

    boost = 0.0
    if query_phrase and query_phrase in text:
        boost += 0.35
    if query_phrase and query_phrase in " ".join([title, authors, tags, genres]):
        boost += 0.25
    if query_terms:
        coverage = sum(1 for term in query_terms if term in searchable) / len(query_terms)
        boost += 0.20 * coverage
    return boost


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", query.casefold())
        if len(token) > 2
    }


def _normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
