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
