from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class EpubSourceError(ValueError):
    """Raised when the configured EPUB source cannot be scanned."""


@dataclass(frozen=True)
class DiscoveredEpub:
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str


def scan_epub_files(books_dir: str | Path) -> list[DiscoveredEpub]:
    source = Path(books_dir).expanduser()
    if not source.exists():
        raise EpubSourceError(f"EPUB source directory does not exist: {source}")
    if not source.is_dir():
        raise EpubSourceError(f"EPUB source path is not a directory: {source}")

    epub_paths = sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() == ".epub"
    )

    return [
        DiscoveredEpub(
            path=path,
            relative_path=path.relative_to(source).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=hash_file(path),
        )
        for path in epub_paths
    ]


def hash_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
