# Librarian

Librarian is a local-first personal library assistant for EPUB collections. It
is meant to ingest books, build a searchable local knowledge base, and answer
questions with citations back to the source text.

The project is also an AI engineering learning ground. It is intentionally
designed around the parts of applied AI that matter in production systems:
ingestion, metadata modeling, chunking, embeddings, retrieval, reranking,
prompt assembly, source attribution, evaluation, and containerized local
infrastructure.

## Goals

- Ingest EPUB files from a configurable local folder.
- Extract useful book, author, chapter, and document structure metadata.
- Chunk books in a way that preserves source context.
- Generate embeddings locally without OpenAI API keys.
- Store source text, metadata, and vectors on this machine.
- Support semantic, keyword, and eventually hybrid retrieval.
- Answer questions across one book, one author, or the whole library.
- Cite the source passages used to produce each answer.
- Keep startup simple with Docker Compose and local volumes.

## Example Questions

Librarian should eventually support questions like:

- "I want to read a book that teaches me about distributed systems."
- "I want a fantasy book with political intrigue and strong worldbuilding."
- "What does this author say about suffering?"
- "Compare how these three books talk about habit formation."
- "Is this book worth reading for learning AI engineering?"
- "Find books in my library that discuss retrieval-augmented generation."

## Local-First Model

The project is designed to avoid OpenAI API-key billing for large book
processing jobs. Full-book ingestion should not call a hosted chat model.
Instead, ingestion is deterministic and local:

1. Parse EPUB files.
2. Clean and normalize text.
3. Split text into source-aware chunks.
4. Generate local embeddings.
5. Store chunks, metadata, and vectors locally.

For answer generation, Librarian can optionally call a host-side Codex broker
after retrieval. That means only the user's question and a small set of relevant
passages are sent to Codex CLI for synthesis. Codex uses the existing Codex
login rather than an OpenAI API key.

Codex is not used as the embedding system. Embeddings require stable numeric
vectors, so they should come from a local embedding model such as
`nomic-embed-text`, `bge-small-en`, `all-MiniLM-L6-v2`, or a similar small
model that can run comfortably on local hardware.

## Architecture

```text
configured EPUB folder
  -> ingestion worker
  -> EPUB parser
  -> text cleaner
  -> structure-aware chunker
  -> local embedding model
  -> local metadata/vector store
  -> retrieval service
  -> optional Codex broker for answer synthesis
  -> web/API clients
```

## Major Components

### EPUB Ingestion

The ingestion layer reads EPUB files from the configured books directory,
extracts metadata, and turns book content into normalized text. EPUB files can
have messy metadata and inconsistent internal structure, so this layer should be
defensive and keep the original file hash for idempotent re-ingestion.

### Chunking

Chunking should preserve where text came from. A chunk should know its book,
author, chapter or section, order within the book, and nearby chunks. This makes
retrieval better and lets answers cite useful locations instead of anonymous
text blobs.

### Local Embeddings

Embedding generation should run locally. The first version can use a lightweight
model through a Python package or local model service. Embeddings are generated
for each chunk and for each query.

### Storage

The MVP should use the simplest local storage that works well. SQLite plus a
lightweight vector option is a good first target. Postgres with pgvector or
OpenSearch can come later once the ingestion and retrieval loop is proven.

### Retrieval

Retrieval starts with semantic vector search. Later versions should add keyword
search and hybrid retrieval so exact terms, names, quotes, and technical phrases
work well alongside semantic queries.

### Generation

Generation happens after retrieval. The generator receives a compact prompt
containing the user question, retrieved passages, and citation metadata. The
answer should cite the passages it uses and clearly say when the retrieved
evidence is insufficient.

### Codex Broker

The broker is a small host-side service that wraps `codex exec`. Containers can
call the broker over HTTP instead of mounting Codex credentials into Docker. It
is optional and should be treated as an answer synthesis layer, not as core
storage or ingestion infrastructure.

## First Target

- Parse EPUBs from the configured books directory.
- Store book, author, chapter, and chunk metadata locally.
- Generate embeddings locally.
- Retrieve relevant chunks for a user query.
- Send only retrieved passages to a generator, with citations.

## Repository Layout

```text
apps/api/              FastAPI application surface
apps/codex_broker/     Host-side Codex CLI wrapper service
packages/ingestion/    EPUB parsing and chunking package
books/                 Optional local EPUB input folder, ignored by Git
Epub-Books/            Local test EPUB folder, ignored by Git
data/                  Local runtime data, ignored by Git
models/                Local model cache/config, ignored by Git
docs/                  Architecture notes
scripts/               Developer helper scripts
```

## Phase Plans

- [Phase 1: EPUB Ingestion MVP](docs/phase-1-ingestor.md)

## Roadmap

### Phase 0: Workspace Foundation

- Create the repository structure.
- Add Docker Compose.
- Add API and ingestion package skeletons.
- Add Codex broker skeleton.
- Document architecture and local-first constraints.

### Phase 1: EPUB Ingestion MVP

See the detailed implementation plan:
[Phase 1: EPUB Ingestion MVP](docs/phase-1-ingestor.md).

- Scan the configured books directory for EPUB files.
- Compute file hashes to skip unchanged books.
- Parse EPUB metadata and text.
- Store book and chunk records locally.
- Add ingestion status reporting.
- Add basic tests with small fixture EPUBs.

### Phase 2: Local Embeddings and Vector Search

- Choose the first local embedding backend.
- Generate embeddings for chunks.
- Store vectors locally.
- Add query embedding generation.
- Return top matching chunks for a query.
- Add a simple `/search` endpoint.

### Phase 3: Retrieval-Augmented Answers

- Build prompt assembly with citation metadata.
- Add `/chat` or `/answer` endpoint.
- Support local generation or Codex broker generation.
- Require answers to cite retrieved passages.
- Add refusal behavior when evidence is weak.

### Phase 4: Better Book Intelligence

- Add author-level and book-level filtering.
- Add recommendation-oriented queries.
- Add genre/topic tagging.
- Add chapter summaries generated only on demand.
- Add saved searches or reading lists.

### Phase 5: Hybrid Retrieval

- Add keyword/BM25 search.
- Combine vector and lexical retrieval.
- Add reranking.
- Improve exact phrase, name, and technical-term search.
- Evaluate retrieval quality with a small benchmark set.

### Phase 6: User Interface

- Add a simple web UI.
- Support library browsing.
- Show ingestion progress.
- Show citations and source passages.
- Support scoped chat over one book, one author, or the whole library.

### Phase 7: Operational Polish

- Add one-command startup.
- Add database migrations.
- Add backup/export guidance.
- Add observability for ingestion and query latency.
- Add error handling for malformed EPUB files.
- Add configuration profiles for small-machine and heavier-machine setups.

## Design Principles

- Keep source text and metadata local.
- Do not use hosted LLM calls during full-book ingestion.
- Prefer deterministic processing before model calls.
- Use small, replaceable interfaces for embedding and generation providers.
- Preserve citations as first-class data.
- Start simple, then swap in heavier infrastructure only when needed.
- Treat retrieval quality as something to measure, not guess.

## Local Development

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "apps/api[dev]" -e "apps/codex_broker[dev]" -e "packages/ingestion[dev]"
```

Start the API:

```bash
uvicorn librarian_api.main:app --app-dir apps/api --reload
```

Or start the container stack:

```bash
docker compose up --build
```

Run the test suite:

```bash
scripts/test.sh
```

Run checks used by pull requests:

```bash
scripts/check.sh
```

Run EPUB ingestion into the local SQLite database:

```bash
python3 scripts/ingest_epubs.py --books-dir ./Epub-Books --database-url sqlite:///data/librarian.db
```

For automation or a future desktop shell, request JSON output:

```bash
python3 scripts/ingest_epubs.py --books-dir ./Epub-Books --database-url sqlite:///data/librarian.db --json
```

The API also exposes ingestion-oriented endpoints that a future Electron or
Tauri frontend can call:

```text
POST /ingestion/run        body: books_dir, database_url, force, list_epubs
GET  /ingestion/summary    query: database_url
GET  /books                query: database_url, status, limit, offset
```

By default, Docker Compose mounts `./Epub-Books` into the API container at
`/books`. To use a different local folder, create a `.env` file and set:

```bash
LIBRARIAN_HOST_BOOKS_DIR=/absolute/path/to/epubs
```

Inside the container, the application reads from `LIBRARIAN_BOOKS_DIR`, which
defaults to `/books`. When running outside Docker, set `LIBRARIAN_BOOKS_DIR`
directly to the local folder you want to ingest from.

## Codex Usage Boundary

Codex is treated as an optional generation layer, not as the embedding system.
Embeddings should come from a small local embedding model. Codex can be called
after retrieval, when the prompt contains only the user question and the top
passages needed for an answer.

The intended pattern is:

```text
large book processing -> local deterministic pipeline
embedding generation  -> local embedding model
retrieval             -> local database/index
final synthesis       -> optional Codex broker
```
