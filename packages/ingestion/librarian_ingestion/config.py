from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

BOOKS_DIR_ENV = "LIBRARIAN_BOOKS_DIR"
DEFAULT_LOCAL_BOOKS_DIR = "Epub-Books"
DEFAULT_CONTAINER_BOOKS_DIR = "/books"


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
