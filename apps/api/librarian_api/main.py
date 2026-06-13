from fastapi import FastAPI

from librarian_api.config import settings

app = FastAPI(title="Librarian", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "books_dir": settings.books_dir,
        "host_books_dir": settings.host_books_dir,
        "codex_broker_enabled": settings.enable_codex_broker,
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Librarian",
        "message": "Local-first EPUB RAG workspace is ready.",
    }
