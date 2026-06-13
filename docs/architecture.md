# Architecture Notes

## Local-First Constraints

- EPUB source files live in `./books`.
- Runtime databases and indexes live in `./data`.
- Embeddings are generated locally.
- OpenAI API keys are not required.
- Codex CLI can be used through a host-side broker after retrieval.

## Why Codex Is Not the Embedding Layer

Embeddings need stable numeric vectors. Codex is useful for agentic reasoning and
answer synthesis, but the CLI does not expose an embeddings endpoint. The
embedding layer should be a small local model so ingestion remains repeatable,
cheap, and independent of hosted API billing.

## Suggested MVP Storage

Start with SQLite plus a lightweight vector extension or local vector library.
Move to Postgres/pgvector or OpenSearch only after the ingestion and retrieval
loop works end to end.

## Query Flow

1. Normalize the user question.
2. Generate a local query embedding.
3. Retrieve candidate chunks from vector and lexical search.
4. Rerank or score candidates.
5. Send top passages to the generator.
6. Return an answer with citations.

