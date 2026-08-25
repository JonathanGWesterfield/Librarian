"""JSON-backed settings consumed by the FastAPI application."""

from __future__ import annotations

from dataclasses import dataclass

from librarian_config.config import get_librarian_config


@dataclass(frozen=True)
class Settings:
    database_url: str
    books_dir: str
    host_books_dir: str
    log_file: str


def get_settings() -> Settings:
    """Load API settings from the required Librarian JSON configuration."""
    config = get_librarian_config()
    return Settings(
        database_url=config.paths.database_url,
        books_dir=config.paths.books_dir,
        host_books_dir=config.paths.host_books_dir,
        log_file=config.paths.log_file,
    )
