# Phase 1: EPUB Ingestion MVP

Phase 1 builds the first real ingestion loop for Librarian. The goal is a
standalone Python script that can scan a configured EPUB directory, parse each
book, extract text, prepare chunks for embeddings, and write local ingestion
artifacts that are easy to inspect.

This phase should not call a hosted LLM and should not require an OpenAI API
key. Embedding generation will be added behind an interface, but the first
version can run without a real embedding model.

## Goals

- Add a standalone ingestion script.
- Read the EPUB source directory from configuration.
- Scan all EPUB files in the configured directory.
- Compute file hashes so unchanged books can be skipped.
- Extract EPUB metadata and text.
- Clean and normalize extracted text.
- Split text into source-aware chunks.
- Write local ingestion output for books, chunks, and manifest state.
- Leave a clear interface for local embedding generation.

## Proposed Entry Point

```text
scripts/ingest_epubs.py
```

Example local usage:

```bash
LIBRARIAN_BOOKS_DIR=./Epub-Books python scripts/ingest_epubs.py
```

Example Docker-oriented usage:

```bash
LIBRARIAN_BOOKS_DIR=/books python scripts/ingest_epubs.py
```

The script should use the same settings model as the API when possible, so the
configured ingestion location stays consistent across local and containerized
runs.

## Pipeline

```text
load settings
  -> scan books directory
  -> compute file hashes
  -> skip unchanged books
  -> parse EPUB files
  -> extract metadata
  -> clean text
  -> chunk text
  -> prepare embedding inputs
  -> write local artifacts
  -> print ingestion summary
```

## Step 1: File Scanning

The scanner should read `LIBRARIAN_BOOKS_DIR`, verify that the directory exists,
and find EPUB files recursively or directly within the configured folder.

Initial behavior:

- Find `*.epub` files.
- Sort paths for deterministic runs.
- Compute SHA-256 for each file.
- Print how many EPUB files were found.
- Fail clearly if the configured directory does not exist.

Initial script:

```bash
python scripts/ingest_epubs.py --books-dir ./Epub-Books --list
```

Machine-readable output for desktop apps and automation:

```bash
python3 scripts/ingest_epubs.py --books-dir ./Epub-Books --database-url sqlite:///data/librarian.db --json
```

## Step 2: EPUB Parsing

Use the ingestion package as the parsing boundary:

```python
from librarian_ingestion import parse_epub
```

The current parser returns a `ParsedBook` with source path, title, authors, and
text. Over time, this should evolve toward a more structured shape:

```python
ParsedBook(
    source_path: str,
    file_hash: str,
    title: str | None,
    authors: list[str],
    chapters: list[ParsedChapter],
)
```

Chapter-aware parsing is not required for the first script, but the code should
avoid making it hard to add later.

## Step 3: Text Cleaning

Normalize extracted text before chunking.

Initial cleaning rules:

- Remove excessive whitespace.
- Normalize line breaks.
- Preserve paragraph boundaries where possible.
- Remove empty sections.
- Avoid stripping punctuation or text that may matter for citations.

The cleaner should be deterministic and easy to test.

## Step 4: Chunking

Chunking turns book text into retrievable passages. The first version can use
character-based chunking, with the implementation isolated so tokenizer-aware
chunking can replace it later.

Initial chunking target:

- Target size: 1,500-2,500 characters.
- Overlap: 200-300 characters.
- Prefer splitting on paragraph boundaries.
- Preserve chunk order within each book.

Proposed chunk shape:

```python
TextChunk(
    book_id: str,
    chunk_index: int,
    title: str | None,
    authors: list[str],
    chapter_title: str | None,
    text: str,
    token_estimate: int,
)
```

## Step 5: Local Persistence

For Phase 1, use SQLite behind a storage adapter. SQLite keeps the first local
implementation simple, inspectable, and serverless, while the adapter lets us
add a Postgres implementation later without rewriting the ingestion pipeline.

Default output path:

```text
data/librarian.db
```

Initial tables:

```text
books
chunks
```

`books` stores source path, relative path, file hash, metadata, ingestion status,
and timestamps. `chunks` stores ordered text chunks linked back to the book.

The ingestor should depend on an adapter protocol rather than SQLite directly:

```python
class IngestionStore:
    def initialize(self) -> None: ...
    def get_book_by_relative_path(self, relative_path: str): ...
    def save_book_with_chunks(self, book, chunks) -> None: ...
```

Postgres is a likely future upgrade when full-text search, pgvector, hybrid
retrieval, or heavier concurrent use become important.

## Desktop/API Integration

The ingestion flow should be easy to trigger from a future Electron or Tauri
desktop app. The current integration points are:

```text
CLI:
  python3 scripts/ingest_epubs.py --json

API:
  POST /ingestion/run        body: books_dir, database_url, force, list_epubs,
                              embed_chunks, embedding_provider, embedding_model,
                              ollama_base_url, embedding_batch_size
  POST /embeddings/rebuild   body: database_url, embedding_provider,
                              embedding_model, ollama_base_url, reset, reset_all
  GET  /ingestion/summary    query: database_url
  GET  /books                query: database_url, status, limit, offset
```

`POST /ingestion/run` executes the same ingestion service as the CLI. `GET
/ingestion/summary` returns book/chunk totals and status counts. `GET /books`
returns stored book records with their ingestion status and chunk counts.

## Step 6: Embedding Interface

Do not hard-code a model provider into the ingestor. Add a small interface that
can be implemented later:

```python
class Embedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...
```

Phase 1 can use a no-op embedder:

```python
class NoopEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return []
```

The first concrete provider target is Ollama. Librarian should track the
provider name, model name, and Ollama base URL in configuration, but model
weights must not live in the repository. They should be pulled into Ollama's
local model cache by the user or by a future setup helper.

Current provider settings:

```bash
LIBRARIAN_EMBEDDING_PROVIDER=ollama
LIBRARIAN_EMBEDDING_MODEL=all-minilm
LIBRARIAN_OLLAMA_BASE_URL=http://localhost:11434
```

Ollama embedding generation should call `POST /api/embed` with `model` and
`input`. The older `/api/embeddings` endpoint is superseded, so new code should
avoid building against it.

Example manual setup:

```bash
ollama pull all-minilm
python3 scripts/rebuild_embeddings.py --reset --embedding-provider ollama --embedding-model all-minilm
```

`scripts/rebuild_embeddings.py` operates only on existing chunk rows. It can
delete embedding rows for a selected provider/model and regenerate vectors
without deleting `books`, `chunks`, or raw text.

Other later implementations can target local providers such as
sentence-transformers, LM Studio, or another local embedding service.

## Step 7: Idempotency

The script should avoid reprocessing unchanged EPUBs. At minimum,
`manifest.json` should store:

```json
{
  "source_path": "...",
  "file_hash": "...",
  "ingested_at": "...",
  "chunk_count": 123
}
```

If an EPUB path and hash are unchanged, the script can skip it. If a file hash
changes, the script should reprocess that book.

## Expected Output

An example successful run:

```text
Librarian EPUB ingestion
Books directory: ./Epub-Books
Database: sqlite:///data/librarian.db
Found 57 EPUB files
Parsed 54
Skipped unchanged 3
Skipped duplicates 0
Failed 0
Stored chunks 4120
Database totals: 54 books, 4120 chunks
```

## First Pull Request Scope

The first implementation PR for this phase should include:

- `scripts/ingest_epubs.py`
- Chunking utilities in `packages/ingestion`
- JSONL persistence under `data/ingestion`
- Config-based `LIBRARIAN_BOOKS_DIR` support
- File hashing and unchanged-file skipping
- Summary output
- Tests for cleaning, chunking, and manifest behavior

Real embedding generation should remain out of scope until the ingestion output
is reliable and easy to inspect.
