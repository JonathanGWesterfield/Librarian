from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

BOOKS_DIR_ENV = "LIBRARIAN_BOOKS_DIR"
DATABASE_URL_ENV = "LIBRARIAN_DATABASE_URL"
EMBEDDING_PROVIDER_ENV = "LIBRARIAN_EMBEDDING_PROVIDER"
EMBEDDING_MODEL_ENV = "LIBRARIAN_EMBEDDING_MODEL"
GENERATION_PROVIDER_ENV = "LIBRARIAN_GENERATION_PROVIDER"
GENERATION_MODEL_ENV = "LIBRARIAN_GENERATION_MODEL"
OLLAMA_BASE_URL_ENV = "LIBRARIAN_OLLAMA_BASE_URL"
DEFAULT_LOCAL_BOOKS_DIR = "Epub-Books"
DEFAULT_CONTAINER_BOOKS_DIR = "/books"
DEFAULT_DATABASE_URL = "sqlite:///data/librarian.db"
DEFAULT_EMBEDDING_PROVIDER = "noop"
DEFAULT_EMBEDDING_MODEL = "all-minilm"
DEFAULT_GENERATION_PROVIDER = "noop"
DEFAULT_GENERATION_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def resolve_books_dir(
    books_dir: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    if books_dir is not None:
        return Path(books_dir).expanduser()

    source_env = env if env is not None else os.environ
    configured = source_env.get(BOOKS_DIR_ENV)
    if configured:
        return Path(configured).expanduser()

    root = cwd if cwd is not None else Path.cwd()
    local_default = root / DEFAULT_LOCAL_BOOKS_DIR
    if local_default.exists():
        return local_default

    return Path(DEFAULT_CONTAINER_BOOKS_DIR)


def resolve_database_url(
    database_url: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if database_url:
        return database_url

    source_env = env if env is not None else os.environ
    return source_env.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


def resolve_embedding_provider(
    embedding_provider: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if embedding_provider:
        return embedding_provider

    source_env = env if env is not None else os.environ
    return source_env.get(EMBEDDING_PROVIDER_ENV, DEFAULT_EMBEDDING_PROVIDER)


def resolve_embedding_model(
    embedding_model: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if embedding_model:
        return embedding_model

    source_env = env if env is not None else os.environ
    return source_env.get(EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL)


def resolve_generation_provider(
    generation_provider: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if generation_provider:
        return generation_provider

    source_env = env if env is not None else os.environ
    return source_env.get(GENERATION_PROVIDER_ENV, DEFAULT_GENERATION_PROVIDER)


def resolve_generation_model(
    generation_model: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if generation_model:
        return generation_model

    source_env = env if env is not None else os.environ
    return source_env.get(GENERATION_MODEL_ENV, DEFAULT_GENERATION_MODEL)


def resolve_ollama_base_url(
    ollama_base_url: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if ollama_base_url:
        return ollama_base_url.rstrip("/")

    source_env = env if env is not None else os.environ
    return source_env.get(OLLAMA_BASE_URL_ENV, DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def sqlite_path_from_url(database_url: str) -> Path:
    if database_url == "sqlite:///:memory:":
        return Path(":memory:")
    if not database_url.startswith("sqlite:///"):
        raise ValueError(f"unsupported database URL for SQLite adapter: {database_url}")

    path = database_url.removeprefix("sqlite:///")
    if path.startswith("/"):
        return Path(path)
    return Path(path).expanduser()
