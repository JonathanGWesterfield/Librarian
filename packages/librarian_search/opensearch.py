from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from urllib import error, request

from librarian_config.config import (
    resolve_database_url,
    resolve_opensearch_index,
    resolve_opensearch_url,
)
from librarian_storage.storage import SearchEmbeddingRecord, create_ingestion_store


class OpenSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenSearchIndexOptions:
    database_url: str | None = None
    opensearch_url: str | None = None
    index_name: str | None = None
    embedding_provider: str = "ollama"
    embedding_model: str = "all-minilm"
    reset: bool = False
    batch_size: int = 250


@dataclass(frozen=True)
class OpenSearchIndexResult:
    database_url: str
    opensearch_url: str
    index_name: str
    embedding_provider: str
    embedding_model: str
    dimensions: int
    documents_seen: int
    documents_indexed: int
    reset: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OpenSearchChunkDocument:
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
    vector: list[float]
    tags: list[str]
    genres: list[str]

    @classmethod
    def from_search_embedding(
        cls,
        record: SearchEmbeddingRecord,
        *,
        tags: list[str],
        genres: list[str],
    ) -> "OpenSearchChunkDocument":
        return cls(
            chunk_id=record.chunk_id,
            book_id=record.book_id,
            relative_path=record.relative_path,
            title=record.title,
            authors=record.authors,
            publisher=record.publisher,
            chunk_index=record.chunk_index,
            text=record.text,
            embedding_provider=record.provider,
            embedding_model=record.model,
            dimensions=record.dimensions,
            vector=record.vector,
            tags=tags,
            genres=genres,
        )

    def to_document(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "book_id": self.book_id,
            "relative_path": self.relative_path,
            "title": self.title,
            "authors": self.authors,
            "publisher": self.publisher,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "dimensions": self.dimensions,
            "vector": self.vector,
            "tags": self.tags,
            "genres": self.genres,
        }


@dataclass(frozen=True)
class OpenSearchHit:
    score: float
    document: OpenSearchChunkDocument


class OpenSearchClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def delete_index(self, index_name: str) -> None:
        try:
            self._request("DELETE", f"/{index_name}")
        except OpenSearchError as exc:
            if "404" not in str(exc):
                raise

    def create_chunk_index(self, index_name: str, *, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("OpenSearch chunk index dimensions must be at least one")
        try:
            self._request(
                "PUT",
                f"/{index_name}",
                {
                    "settings": {
                        "index": {
                            "knn": True,
                        }
                    },
                    "mappings": {
                        "properties": {
                            "chunk_id": {"type": "keyword"},
                            "book_id": {"type": "keyword"},
                            "relative_path": {"type": "keyword"},
                            "title": {
                                "type": "text",
                                "fields": {"keyword": {"type": "keyword"}},
                            },
                            "authors": {"type": "keyword"},
                            "publisher": {"type": "keyword"},
                            "chunk_index": {"type": "integer"},
                            "text": {"type": "text"},
                            "embedding_provider": {"type": "keyword"},
                            "embedding_model": {"type": "keyword"},
                            "dimensions": {"type": "integer"},
                            "tags": {"type": "keyword"},
                            "genres": {"type": "keyword"},
                            "vector": {
                                "type": "knn_vector",
                                "dimension": dimensions,
                            },
                        }
                    },
                },
            )
        except OpenSearchError as exc:
            if "resource_already_exists_exception" not in str(exc):
                raise

    def bulk_index_chunks(
        self,
        index_name: str,
        documents: list[OpenSearchChunkDocument],
    ) -> int:
        if not documents:
            return 0
        lines: list[str] = []
        for document in documents:
            lines.append(
                json.dumps(
                    {
                        "index": {
                            "_index": index_name,
                            "_id": document.chunk_id,
                        }
                    }
                )
            )
            lines.append(json.dumps(document.to_document()))
        payload = "\n".join(lines) + "\n"
        response = self._request("POST", "/_bulk", raw_body=payload)
        if response.get("errors"):
            raise OpenSearchError("OpenSearch bulk indexing reported errors")
        return len(documents)

    def search_hybrid(
        self,
        index_name: str,
        *,
        query: str,
        vector: list[float],
        provider: str,
        model: str,
        limit: int,
        book_id: str | None = None,
        book_title: str | None = None,
        author: str | None = None,
        genre: str | None = None,
        tag: str | None = None,
    ) -> list[OpenSearchHit]:
        keyword_hits = self.search_keyword(
            index_name,
            query=query,
            provider=provider,
            model=model,
            limit=limit,
            book_id=book_id,
            book_title=book_title,
            author=author,
            genre=genre,
            tag=tag,
        )
        vector_hits = self.search_vector(
            index_name,
            vector=vector,
            provider=provider,
            model=model,
            limit=limit,
            book_id=book_id,
            book_title=book_title,
            author=author,
            genre=genre,
            tag=tag,
        )
        return _merge_hits(keyword_hits, vector_hits, limit=limit)

    def search_keyword(
        self,
        index_name: str,
        *,
        query: str,
        provider: str,
        model: str,
        limit: int,
        book_id: str | None = None,
        book_title: str | None = None,
        author: str | None = None,
        genre: str | None = None,
        tag: str | None = None,
    ) -> list[OpenSearchHit]:
        payload = {
            "size": max(1, limit),
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "text^3",
                                    "title^2",
                                    "authors",
                                    "tags^2",
                                    "genres",
                                ],
                            }
                        }
                    ],
                    "filter": _opensearch_filters(
                        provider=provider,
                        model=model,
                        book_id=book_id,
                        book_title=book_title,
                        author=author,
                        genre=genre,
                        tag=tag,
                    ),
                }
            },
        }
        return self._parse_search_hits(
            self._request("POST", f"/{index_name}/_search", payload)
        )

    def search_vector(
        self,
        index_name: str,
        *,
        vector: list[float],
        provider: str,
        model: str,
        limit: int,
        book_id: str | None = None,
        book_title: str | None = None,
        author: str | None = None,
        genre: str | None = None,
        tag: str | None = None,
    ) -> list[OpenSearchHit]:
        if not vector:
            return []
        payload = {
            "size": max(1, limit),
            "query": {
                "knn": {
                    "vector": {
                        "vector": vector,
                        "k": max(1, limit),
                        "filter": {
                            "bool": {
                                "filter": _opensearch_filters(
                                    provider=provider,
                                    model=model,
                                    book_id=book_id,
                                    book_title=book_title,
                                    author=author,
                                    genre=genre,
                                    tag=tag,
                                )
                            }
                        },
                    }
                }
            },
        }
        return self._parse_search_hits(
            self._request("POST", f"/{index_name}/_search", payload)
        )

    def _parse_search_hits(self, payload: dict[str, object]) -> list[OpenSearchHit]:
        hits_payload = payload.get("hits", {})
        if not isinstance(hits_payload, dict):
            return []
        raw_hits = hits_payload.get("hits", [])
        if not isinstance(raw_hits, list):
            return []

        hits: list[OpenSearchHit] = []
        for raw_hit in raw_hits:
            if not isinstance(raw_hit, dict):
                continue
            source = raw_hit.get("_source")
            if not isinstance(source, dict):
                continue
            hits.append(
                OpenSearchHit(
                    score=float(raw_hit.get("_score") or 0.0),
                    document=_document_from_source(source),
                )
            )
        return hits

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        raw_body: str | None = None,
    ) -> dict[str, object]:
        if body is not None and raw_body is not None:
            raise ValueError("use body or raw_body, not both")
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        elif raw_body is not None:
            data = raw_body.encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(
                http_request,
                timeout=self.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise OpenSearchError(
                f"OpenSearch request failed with HTTP {exc.code}: "
                f"{method} {path}: {error_body}"
            ) from exc
        except error.URLError as exc:
            raise OpenSearchError(
                f"could not reach OpenSearch at {self.base_url}: {exc}"
            ) from exc
        if not response_body:
            return {}
        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise OpenSearchError("OpenSearch returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise OpenSearchError("OpenSearch returned an unexpected JSON payload")
        return decoded


def index_chunks(options: OpenSearchIndexOptions) -> OpenSearchIndexResult:
    database_url = resolve_database_url(options.database_url)
    opensearch_url = resolve_opensearch_url(options.opensearch_url)
    index_name = resolve_opensearch_index(options.index_name)
    documents = _load_index_documents(
        database_url,
        provider=options.embedding_provider,
        model=options.embedding_model,
    )
    dimensions = documents[0].dimensions if documents else 0
    client = OpenSearchClient(opensearch_url)
    if options.reset:
        client.delete_index(index_name)
    if dimensions:
        client.create_chunk_index(index_name, dimensions=dimensions)

    indexed = 0
    batch_size = max(1, options.batch_size)
    for start in range(0, len(documents), batch_size):
        indexed += client.bulk_index_chunks(index_name, documents[start : start + batch_size])

    return OpenSearchIndexResult(
        database_url=database_url,
        opensearch_url=opensearch_url,
        index_name=index_name,
        embedding_provider=options.embedding_provider,
        embedding_model=options.embedding_model,
        dimensions=dimensions,
        documents_seen=len(documents),
        documents_indexed=indexed,
        reset=options.reset,
    )


def _load_index_documents(
    database_url: str,
    *,
    provider: str,
    model: str,
) -> list[OpenSearchChunkDocument]:
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        records = store.list_search_embeddings(provider=provider, model=model)
        tags_by_book: dict[str, list[str]] = {}
        for tag in store.list_book_tags():
            tags_by_book.setdefault(tag.book_id, []).append(tag.tag)
        genres_by_book: dict[str, list[str]] = {}
        for genre in store.list_book_genres():
            genres_by_book.setdefault(genre.book_id, []).append(genre.genre)
    finally:
        store.close()

    return [
        OpenSearchChunkDocument.from_search_embedding(
            record,
            tags=tags_by_book.get(record.book_id, []),
            genres=genres_by_book.get(record.book_id, []),
        )
        for record in records
    ]


def _opensearch_filters(
    *,
    provider: str,
    model: str,
    book_id: str | None,
    book_title: str | None,
    author: str | None,
    genre: str | None,
    tag: str | None,
) -> list[dict[str, object]]:
    filters: list[dict[str, object]] = [
        {"term": {"embedding_provider": provider}},
        {"term": {"embedding_model": model}},
    ]
    if book_id:
        filters.append({"term": {"book_id": book_id}})
    if book_title:
        filters.append({"match_phrase": {"title": book_title}})
    if author:
        filters.append({"term": {"authors": author}})
    if genre:
        filters.append({"term": {"genres": genre}})
    if tag:
        filters.append({"term": {"tags": tag}})
    return filters


def _merge_hits(
    keyword_hits: list[OpenSearchHit],
    vector_hits: list[OpenSearchHit],
    *,
    limit: int,
) -> list[OpenSearchHit]:
    keyword_scores = _normalized_scores(keyword_hits)
    vector_scores = _normalized_scores(vector_hits)
    docs: dict[str, OpenSearchChunkDocument] = {}
    for hit in [*keyword_hits, *vector_hits]:
        docs[hit.document.chunk_id] = hit.document

    merged: list[OpenSearchHit] = []
    for chunk_id, document in docs.items():
        score = (0.45 * keyword_scores.get(chunk_id, 0.0)) + (
            0.55 * vector_scores.get(chunk_id, 0.0)
        )
        merged.append(OpenSearchHit(score=score, document=document))
    merged.sort(key=lambda hit: hit.score, reverse=True)
    return merged[: max(1, limit)]


def _normalized_scores(hits: list[OpenSearchHit]) -> dict[str, float]:
    if not hits:
        return {}
    max_score = max(hit.score for hit in hits) or 1.0
    return {
        hit.document.chunk_id: hit.score / max_score
        for hit in hits
    }


def _document_from_source(source: dict[str, object]) -> OpenSearchChunkDocument:
    return OpenSearchChunkDocument(
        chunk_id=str(source["chunk_id"]),
        book_id=str(source["book_id"]),
        relative_path=str(source["relative_path"]),
        title=_optional_str(source.get("title")),
        authors=[str(author) for author in source.get("authors", [])],
        publisher=_optional_str(source.get("publisher")),
        chunk_index=int(source["chunk_index"]),
        text=str(source["text"]),
        embedding_provider=str(source["embedding_provider"]),
        embedding_model=str(source["embedding_model"]),
        dimensions=int(source["dimensions"]),
        vector=[float(value) for value in source.get("vector", [])],
        tags=[str(tag) for tag in source.get("tags", [])],
        genres=[str(genre) for genre in source.get("genres", [])],
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
