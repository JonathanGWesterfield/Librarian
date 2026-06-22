# Librarian API Contract

The programmatic API contract lives in [openapi.json](openapi.json).

FastAPI also serves a generated OpenAPI document at runtime:

```text
http://localhost:8000/openapi.json
```

Use the static spec in this folder when a client, desktop shell, code generator,
or test harness needs to ingest the API without starting the service.

Default local base URL:

```text
http://localhost:8000
```

Default local database:

```text
sqlite:///data/librarian.db
```

Common error behavior:

- `400`: invalid input, unsupported provider/database URL, missing EPUB source,
  or local embedding service failure.
- `422`: request body or query parameters do not match FastAPI/Pydantic
  validation.

## Ingestion

### `POST /ingestion/run`

Scans EPUB files, parses text, chunks books, stores book/chunk records, can
generate chunk embeddings, and can enqueue asynchronous chapter/book summary
jobs for newly ingested books.

Summary queueing is deliberately separate from summary generation. When
`enqueue_summaries` is true, ingestion writes durable `pending` summary jobs and
returns without calling the summarizer LLM. A worker such as
`scripts/process_summary_jobs.py` drains those jobs later.

Request fields:

- `books_dir`: EPUB source directory. Defaults to `LIBRARIAN_BOOKS_DIR`.
- `database_url`: local storage URL. Defaults to `LIBRARIAN_DATABASE_URL`.
- `force`: re-parse unchanged EPUB files.
- `list_epubs`: include discovered EPUB metadata in the response.
- `embed_chunks`: generate embeddings for chunks created during the run.
- `embedding_provider`: embedding provider, such as `noop` or `ollama`.
- `embedding_model`: embedding model name.
- `ollama_base_url`: optional Ollama URL override.
- `embedding_batch_size`: chunk embedding batch size.
- `enqueue_summaries`: queue asynchronous summary jobs for newly ingested books.
- `summary_generation_provider`: queued summary provider, such as `codex` or
  `ollama`.
- `summary_generation_model`: queued summary model.
- `summary_detail`: queued summary detail level: `short`, `medium`, or
  `detailed`.

Ingest and queue summaries:

```json
{
  "books_dir": "/books",
  "database_url": "sqlite:///data/librarian.db",
  "enqueue_summaries": true,
  "summary_generation_provider": "codex",
  "summary_generation_model": "codex",
  "summary_detail": "medium"
}
```

Ingest, embed, and queue summaries:

```json
{
  "books_dir": "/books",
  "database_url": "sqlite:///data/librarian.db",
  "embed_chunks": true,
  "embedding_provider": "ollama",
  "embedding_model": "all-minilm",
  "enqueue_summaries": true,
  "summary_generation_provider": "ollama",
  "summary_generation_model": "llama3.2:3b"
}
```

Response:

- `found`, `parsed`, `skipped_unchanged`, `skipped_duplicates`, `failed`:
  ingestion counters.
- `stored_chunks`: chunks stored during this run.
- `stored_embeddings`: embeddings stored during this run.
- `summary_jobs_enqueued`: asynchronous summary jobs queued during this run.
- `total_books`, `total_chunks`, `total_embeddings`: database totals after the
  run.
- `books`: per-book ingestion results.
- `discovered`: optional discovered EPUB metadata when `list_epubs` is true.

## Book Genres

### `POST /books/{book_id}/genres`

Generates or reuses broad bookstore/library genres for one stored book. The
target book must already have a stored book summary for the selected
`source_summary_provider`, `source_summary_model`, and `source_summary_detail`.

Request fields:

- `database_url`: optional SQLite database URL. Defaults to
  `LIBRARIAN_DATABASE_URL`.
- `source_summary_provider`: optional summary provider to read from, such as
  `codex` or `ollama`.
- `source_summary_model`: optional summary model to read from.
- `source_summary_detail`: summary detail level. One of `short`, `medium`, or
  `detailed`; defaults to `medium`.
- `generation_provider`: optional genre generation provider. One of `codex`,
  `ollama`, or `noop`.
- `generation_model`: optional model for the generation provider.
- `ollama_base_url`: optional Ollama URL override.
- `max_secondary_genres`: maximum secondary genres to generate. Defaults to `3`.
- `force_refresh`: regenerate even when cached genres exist.
- `reset`: delete existing generated genres for the book before regenerating.

Example payload:

```json
{
  "database_url": "sqlite:///data/librarian.db",
  "source_summary_provider": "codex",
  "source_summary_model": "codex",
  "generation_provider": "codex",
  "generation_model": "codex",
  "max_secondary_genres": 3
}
```

Reset and rebuild with Ollama:

```json
{
  "database_url": "sqlite:///data/librarian.db",
  "source_summary_provider": "codex",
  "source_summary_model": "codex",
  "generation_provider": "ollama",
  "generation_model": "llama3.2:3b",
  "reset": true
}
```

Response:

- `book_id`, `title`, `authors`: target book identity.
- `source_summary_provider`, `source_summary_model`,
  `source_summary_detail`: summary used as the classification source.
- `generation_provider`, `generation_model`: model that generated the genres.
- `deleted_genres`: genres deleted before rebuild.
- `generated_genres`: new genres generated in this call.
- `cached_genres`: cached genres reused in this call.
- `genres`: generated or cached genre records with `genre`, `genre_role`,
  `confidence`, `rationale`, and `cached`.

### `GET /books/{book_id}/genres`

Lists stored genres for one book.

Query parameters:

- `database_url`: optional SQLite database URL.
- `genre_role`: optional `primary` or `secondary` filter.
- `source`: optional source filter, such as `llm`.
- `provider`: optional generation provider filter.
- `model`: optional generation model filter.

Example:

```text
GET /books/forward-foundation/genres?database_url=sqlite:///data/librarian.db&genre_role=primary
```

Response:

```json
[
  {
    "id": "book-genre:...",
    "book_id": "forward-foundation",
    "genre": "Science Fiction",
    "genre_role": "primary",
    "source": "llm",
    "confidence": 0.96,
    "provider": "codex",
    "model": "codex",
    "rationale": "Foundation is science fiction.",
    "created_at": "2026-06-22T00:00:00+00:00",
    "updated_at": "2026-06-22T00:00:00+00:00"
  }
]
```

### `DELETE /books/{book_id}/genres`

Deletes stored generated genre records for one book. This is intended for
benchmarking prompt/model changes and rebuilding genre metadata.

Query parameters:

- `database_url`: optional SQLite database URL.
- `genre_role`: optional `primary` or `secondary` filter.
- `source`: optional source filter. Defaults to `llm`.

Example:

```text
DELETE /books/forward-foundation/genres?database_url=sqlite:///data/librarian.db&source=llm
```

Response:

```json
{
  "deleted_genres": 2
}
```
