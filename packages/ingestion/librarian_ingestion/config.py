from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

BOOKS_DIR_ENV = "LIBRARIAN_BOOKS_DIR"
DATABASE_URL_ENV = "LIBRARIAN_DATABASE_URL"
DEFAULT_LOCAL_BOOKS_DIR = "Epub-Books"
DEFAULT_CONTAINER_BOOKS_DIR = "/books"
DEFAULT_DATABASE_URL = "sqlite:///data/librarian.db"


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


def sqlite_path_from_url(database_url: str) -> Path:
    if database_url == "sqlite:///:memory:":
        return Path(":memory:")
    if not database_url.startswith("sqlite:///"):
        raise ValueError(f"unsupported database URL for SQLite adapter: {database_url}")

    path = database_url.removeprefix("sqlite:///")
    if path.startswith("/"):
        return Path(path)
    return Path(path).expanduser()
