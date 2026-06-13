from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from librarian_ingestion.epub import ParsedBook
    from librarian_ingestion.scan import DiscoveredEpub, EpubSourceError

__all__ = [
    "DiscoveredEpub",
    "EpubSourceError",
    "ParsedBook",
    "parse_epub",
    "scan_epub_files",
]


def __getattr__(name: str):
    if name in {"ParsedBook", "parse_epub"}:
        from librarian_ingestion.epub import ParsedBook, parse_epub

        return {"ParsedBook": ParsedBook, "parse_epub": parse_epub}[name]

    if name in {"DiscoveredEpub", "EpubSourceError", "scan_epub_files"}:
        from librarian_ingestion.scan import (
            DiscoveredEpub,
            EpubSourceError,
            scan_epub_files,
        )

        return {
            "DiscoveredEpub": DiscoveredEpub,
            "EpubSourceError": EpubSourceError,
            "scan_epub_files": scan_epub_files,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
