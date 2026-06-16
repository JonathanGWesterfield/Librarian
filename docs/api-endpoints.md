# FastAPI Endpoint Reference

Librarian's API is a local-first control surface for ingestion, embedding
maintenance, and read-only library inspection. The API wraps package services;
the business logic does not live in the route handlers.

Default local base URL:

```text
http://localhost:8000
```

Most endpoints use the configured database unless `database_url` is supplied.
The default database is:

```text
sqlite:///data/librarian.db
```

Common error behavior:

- `400`: invalid input, unsupported provider/database URL, missing EPUB source,
  or local embedding service failure.
- `422`: request body or query parameters do not match FastAPI/Pydantic
  validation.

## GET `/health`

Returns basic API configuration and service health.

### Request Fields

No request body or query parameters.

### Example Requests

```bash
curl http://localhost:8000/health
```

```bash
curl -s http://localhost:8000/health | jq
```

### Response

Fields:

- `status`: `"ok"` when the API process is responding.
- `books_dir`: container/API EPUB directory.
- `host_books_dir`: host EPUB directory configured for local Docker mounts.
- `codex_broker_enabled`: whether the optional Codex broker is enabled.

Example:

```json
{
  "status": "ok",
  "books_dir": "/books",
  "host_books_dir": "./Epub-Books",
  "codex_broker_enabled": false
}
```

## GET `/`

Returns a small API identity payload.

### Request Fields

No request body or query parameters.

### Example Requests

```bash
curl http://localhost:8000/
```

```bash
curl -s http://localhost:8000/ | jq
```

### Response

Fields:

- `name`: application name.
- `message`: short readiness message.

Example:

```json
{
  "name": "Librarian",
  "message": "Local-first EPUB RAG workspace is ready."
}
```

## POST `/ingestion/run`

Scans EPUB files, parses text, chunks books, stores `books` and `chunks`, and
optionally generates embeddings for newly ingested chunks.

This endpoint delegates to `librarian_ingestion.ingest.run_ingestion`.

### Request Fields

- `books_dir`: optional string. EPUB source directory. Defaults to API
  `LIBRARIAN_BOOKS_DIR`.
- `database_url`: optional string. Storage URL. Defaults to
  `LIBRARIAN_DATABASE_URL`.
- `force`: boolean, default `false`. Re-parse unchanged EPUB files.
- `list_epubs`: boolean, default `false`. Include discovered EPUB metadata in
  the response.
- `embed_chunks`: boolean, default `false`. Generate embeddings for chunks
  created during this ingestion run.
- `embedding_provider`: optional string. Currently `noop` or `ollama`.
- `embedding_model`: optional string. Model name, such as `all-minilm`.
- `ollama_base_url`: optional string. Ollama base URL, such as
  `http://host.docker.internal:11434`.
- `embedding_batch_size`: integer, default `16`. Number of chunks to send to
  the embedder per request.

### Example Payloads

Ingest EPUBs without generating embeddings:

```json
{
  "books_dir": "/books",
  "database_url": "sqlite:///data/librarian.db",
  "list_epubs": true
}
```

Ingest and embed with Ollama:

```json
{
  "books_dir": "/books",
  "database_url": "sqlite:///data/librarian.db",
  "force": false,
  "embed_chunks": true,
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "ollama_base_url": "http://host.docker.internal:11434",
  "embedding_batch_size": 16
}
```

### Example Requests

```bash
curl -X POST http://localhost:8000/ingestion/run \
  -H 'Content-Type: application/json' \
  -d '{"books_dir":"/books","database_url":"sqlite:///data/librarian.db"}'
```

```bash
curl -X POST http://localhost:8000/ingestion/run \
  -H 'Content-Type: application/json' \
  -d '{"books_dir":"/books","embed_chunks":true,"embedding_provider":"ollama","embedding_model":"all-minilm"}'
```

### Response

Fields:

- `books_dir`: resolved EPUB source directory.
- `database_url`: resolved storage URL.
- `embedding_provider`: resolved embedding provider.
- `embedding_model`: resolved embedding model.
- `found`: number of EPUB files discovered.
- `parsed`: number of EPUBs parsed and stored as ingested.
- `skipped_unchanged`: number skipped because path/hash/status were unchanged.
- `skipped_duplicates`: number marked duplicate by metadata.
- `failed`: number that failed parsing or storage.
- `stored_chunks`: chunks written during this run.
- `stored_embeddings`: embeddings written during this run.
- `total_books`: total book rows after the run.
- `total_chunks`: total chunk rows after the run.
- `total_embeddings`: total embedding rows after the run.
- `books`: per-book ingestion results.
- `discovered`: discovered EPUB metadata when `list_epubs` is true.

Example:

```json
{
  "books_dir": "/books",
  "database_url": "sqlite:///data/librarian.db",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "found": 59,
  "parsed": 59,
  "skipped_unchanged": 0,
  "skipped_duplicates": 0,
  "failed": 0,
  "stored_chunks": 30780,
  "stored_embeddings": 0,
  "total_books": 59,
  "total_chunks": 30780,
  "total_embeddings": 0,
  "books": [
    {
      "relative_path": "Example.epub",
      "file_hash": "abc123...",
      "status": "ingested",
      "chunk_count": 512,
      "message": null
    }
  ],
  "discovered": []
}
```

## GET `/ingestion/summary`

Returns counts and status totals for the ingestion database.

### Query Parameters

- `database_url`: optional string. Storage URL to inspect. Defaults to
  `LIBRARIAN_DATABASE_URL`.

### Example Requests

```bash
curl 'http://localhost:8000/ingestion/summary'
```

```bash
curl 'http://localhost:8000/ingestion/summary?database_url=sqlite:///data/librarian.db'
```

### Response

Fields:

- `total_books`: total rows in `books`.
- `total_chunks`: total rows in `chunks`.
- `total_embeddings`: total rows in `chunk_embeddings`.
- `status_counts`: object keyed by book ingestion status.

Example:

```json
{
  "total_books": 59,
  "total_chunks": 30780,
  "total_embeddings": 30780,
  "status_counts": {
    "ingested": 59
  }
}
```

## POST `/embeddings/rebuild`

Regenerates embeddings from existing `chunks` rows without deleting `books`,
`chunks`, or raw text.

This endpoint delegates to `librarian_ingestion.embedding_ops.rebuild_embeddings`.

### Request Fields

- `database_url`: optional string. Storage URL. Defaults to
  `LIBRARIAN_DATABASE_URL`.
- `embedding_provider`: optional string. Currently `noop` or `ollama`.
- `embedding_model`: optional string. Model name, such as `all-minilm`.
- `ollama_base_url`: optional string. Ollama base URL.
- `batch_size`: integer, default `16`. Number of chunks per embedding request.
- `chunk_page_size`: integer, default `500`. Number of stored chunks to read
  from the database at a time.
- `reset`: boolean, default `false`. Delete embeddings for the selected
  provider/model before rebuilding.
- `reset_all`: boolean, default `false`. Delete all embeddings before
  rebuilding the selected provider/model.

### Example Payloads

Rebuild embeddings for the current model:

```json
{
  "database_url": "sqlite:///data/librarian.db",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "reset": true
}
```

Benchmark a different model by clearing all existing embedding rows first:

```json
{
  "database_url": "sqlite:///data/librarian.db",
  "embedding_provider": "ollama",
  "embedding_model": "nomic-embed-text",
  "ollama_base_url": "http://host.docker.internal:11434",
  "batch_size": 8,
  "chunk_page_size": 250,
  "reset_all": true
}
```

### Example Requests

```bash
curl -X POST http://localhost:8000/embeddings/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"embedding_provider":"ollama","embedding_model":"all-minilm","reset":true}'
```

```bash
curl -X POST http://localhost:8000/embeddings/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"embedding_provider":"noop","reset":true}'
```

### Response

Fields:

- `database_url`: resolved storage URL.
- `embedding_provider`: resolved provider used.
- `embedding_model`: resolved model used.
- `chunks_seen`: number of chunks read from storage.
- `embeddings_deleted`: number of embedding rows deleted before rebuild.
- `embeddings_stored`: number of embedding rows stored.
- `total_embeddings`: total embedding rows after rebuild.

Example:

```json
{
  "database_url": "sqlite:///data/librarian.db",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "chunks_seen": 30780,
  "embeddings_deleted": 30780,
  "embeddings_stored": 30780,
  "total_embeddings": 30780
}
```

## POST `/embeddings/query`

Creates an embedding vector for a user query. Use this when you want to inspect
the raw query vector directly; most clients should call `POST /search` for the
full retrieval flow.

This endpoint delegates to `librarian_ingestion.embedding_ops.embed_query`.

### Request Fields

- `query`: required string. User search/query text. Must not be empty.
- `embedding_provider`: optional string. Currently `noop` or `ollama`.
- `embedding_model`: optional string. Model name, such as `all-minilm`.
- `ollama_base_url`: optional string. Ollama base URL.

### Example Payloads

Embed a query with the default local model:

```json
{
  "query": "books about memory and identity",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm"
}
```

Use the no-op provider for API shape testing:

```json
{
  "query": "clockwork gardens",
  "embedding_provider": "noop"
}
```

### Example Requests

```bash
curl -X POST http://localhost:8000/embeddings/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"books about memory and identity","embedding_provider":"ollama","embedding_model":"all-minilm"}'
```

```bash
curl -X POST http://localhost:8000/embeddings/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"clockwork gardens","embedding_provider":"noop"}'
```

### Response

Fields:

- `query`: normalized query string after trimming whitespace.
- `embedding_provider`: resolved provider used.
- `embedding_model`: resolved model used.
- `dimensions`: vector length.
- `vector`: embedding vector. Empty when using the `noop` provider.

Example:

```json
{
  "query": "books about memory and identity",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "dimensions": 384,
  "vector": [0.0123, -0.0456, 0.0789]
}
```

## POST `/search`

Embeds a user query, loads stored chunk embeddings for the same provider/model,
scores them with cosine similarity, and returns the top matching chunks with
book metadata.

This endpoint delegates to `librarian_ingestion.search.search_chunks`.

### Request Fields

- `query`: required string. User search/query text. Must not be empty.
- `database_url`: optional string. Storage URL. Defaults to
  `LIBRARIAN_DATABASE_URL`.
- `embedding_provider`: optional string. Currently `noop` or `ollama`.
- `embedding_model`: optional string. Model name, such as `all-minilm`.
- `ollama_base_url`: optional string. Ollama base URL.
- `limit`: integer, default `10`. Maximum number of ranked chunks to return.

### Example Payloads

Search with the default local model:

```json
{
  "query": "what does the author say about memory?",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "limit": 5
}
```

Search an explicit local database:

```json
{
  "query": "fantasy books with political intrigue",
  "database_url": "sqlite:///data/librarian.db",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "ollama_base_url": "http://host.docker.internal:11434",
  "limit": 10
}
```

### Example Requests

```bash
curl -X POST http://localhost:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"what does the author say about memory?","embedding_provider":"ollama","embedding_model":"all-minilm","limit":5}'
```

```bash
curl -X POST http://localhost:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"fantasy books with political intrigue","database_url":"sqlite:///data/librarian.db","embedding_provider":"ollama","embedding_model":"all-minilm","limit":10}'
```

### Response

Fields:

- `query`: normalized query string after trimming whitespace.
- `embedding_provider`: resolved provider used for the query vector.
- `embedding_model`: resolved model used for the query vector.
- `dimensions`: query vector length.
- `candidate_count`: number of compatible stored chunk embeddings scored.
- `results`: ranked chunk matches, highest cosine similarity first.

Fields per result:

- `score`: cosine similarity between query vector and chunk vector.
- `chunk_id`: internal chunk ID linked to the raw text and embedding row.
- `book_id`: internal book ID.
- `relative_path`: EPUB path relative to the configured books directory.
- `title`: parsed EPUB title, when available.
- `authors`: parsed EPUB author list.
- `publisher`: parsed EPUB publisher, when available.
- `chunk_index`: chunk position within the book.
- `text`: raw chunk text used to generate the stored embedding.
- `embedding_provider`: provider for the stored chunk embedding.
- `embedding_model`: model for the stored chunk embedding.
- `dimensions`: stored chunk vector length.

Example:

```json
{
  "query": "what does the author say about memory?",
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "dimensions": 384,
  "candidate_count": 30780,
  "results": [
    {
      "score": 0.8123,
      "chunk_id": "abc123:42",
      "book_id": "abc123",
      "relative_path": "Example.epub",
      "title": "Example Book",
      "authors": ["Example Author"],
      "publisher": "Example Press",
      "chunk_index": 42,
      "text": "Memory is not a fixed archive...",
      "embedding_provider": "ollama",
      "embedding_model": "all-minilm",
      "dimensions": 384
    }
  ]
}
```

## GET `/books`

Returns stored book records with ingestion status and chunk counts.

### Query Parameters

- `status`: optional string. Filter by book ingestion status, such as
  `ingested`, `duplicate`, or `failed`.
- `limit`: integer, default `100`, minimum `1`, maximum `500`.
- `offset`: integer, default `0`, minimum `0`.
- `database_url`: optional string. Storage URL to inspect.

### Example Requests

```bash
curl 'http://localhost:8000/books?limit=10'
```

```bash
curl 'http://localhost:8000/books?status=ingested&limit=5&offset=10&database_url=sqlite:///data/librarian.db'
```

### Response

Returns an array of book records.

Fields per item:

- `id`: internal book ID.
- `relative_path`: EPUB path relative to the configured books directory.
- `title`: parsed EPUB title, when available.
- `authors`: parsed EPUB author list.
- `publisher`: parsed EPUB publisher, when available.
- `status`: ingestion status.
- `error_message`: parsing/storage error for failed books.
- `chunk_count`: number of chunks linked to the book.

Example:

```json
[
  {
    "id": "abc123...",
    "relative_path": "Example.epub",
    "title": "Example Book",
    "authors": ["Example Author"],
    "publisher": "Example Press",
    "status": "ingested",
    "error_message": null,
    "chunk_count": 512
  }
]
```
