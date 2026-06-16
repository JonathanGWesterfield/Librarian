# Architecture Notes

## Local-First Constraints

- EPUB source files live in a configurable local folder.
- The default local test folder is `./Epub-Books`, which is ignored by Git.
- Runtime databases and indexes live in `./data`.
- Embeddings are generated locally through Ollama.
- OpenAI API keys are not required.
- Codex CLI can be used through a host-side broker after retrieval.

## Why Codex Is Not the Embedding Layer

Embeddings need stable numeric vectors. Codex is useful for agentic reasoning and
answer synthesis, but the CLI does not expose an embeddings endpoint. The
embedding layer should be a small local model so ingestion remains repeatable,
cheap, and independent of hosted API billing.

## Current MVP Storage

The current MVP uses SQLite through `SQLiteIngestionStore`. The storage adapter
owns SQLite-specific SQL and exposes repository-style methods to the rest of
the app. Runtime tables include:

```text
books
chunks
chunk_embeddings
```

`books` stores EPUB metadata, file hashes, ingestion status, and source paths.
`chunks` stores raw chunk text linked to each book. `chunk_embeddings` stores
embedding vectors linked back to exact chunk IDs, plus provider/model metadata.

Do not try to keep SQL generic across databases. When Postgres becomes useful,
add a `PostgresIngestionStore` behind the existing store protocol and use
Postgres-native features such as `jsonb` and `pgvector`.

## Current Local Runtime

For local development on macOS, Librarian expects:

```text
Docker/Compose for the API container
native Ollama for embedding generation
SQLite under ./data for runtime storage
```

The setup/start/stop helpers live in `scripts/`. Interactive development tools
live under `scripts/play/`.

## Query Flow

1. Normalize the user question.
2. Generate a local query embedding.
3. Retrieve candidate chunks from stored embeddings.
4. Return top chunks with book metadata, chunk text, and similarity scores.
5. Later, combine vector results with lexical search and reranking.
6. Send top passages to the generator.
7. Return an answer with citations.

The immediate next implementation step is a simple vector retrieval loop over
stored SQLite embeddings. Query embedding is exposed through
`POST /embeddings/query`; retrieval can use that vector to compute cosine
similarity in Python first, then move to a vector extension or Postgres/pgvector
after retrieval behavior is proven end to end.
