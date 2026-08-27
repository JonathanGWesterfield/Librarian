from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from typing import Optional
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT
from ebooklib import epub
from pydantic import BaseModel, Field


BODY_CONTENT_TYPE = "body"
FRONT_MATTER_CONTENT_TYPE = "front_matter"
BACK_MATTER_CONTENT_TYPE = "back_matter"

_FRONT_MATTER_PATH_MARKERS = (
    "copyright",
    "colophon",
    "imprint",
    "titlepage",
    "title-page",
    "frontmatter",
    "front-matter",
    "dedication",
    "epigraph",
    "contents",
    "toc",
    "catalog",
    "publisher",
    "isbn",
    "license",
)
_BACK_MATTER_PATH_MARKERS = (
    "backmatter",
    "back-matter",
    "also-by",
    "also_by",
    "about-author",
    "about_author",
    "about-publisher",
    "about_publisher",
    "advert",
    "other-books",
    "other_books",
    "index",
)
_FRONT_MATTER_TEXT_MARKERS = (
    "all rights reserved",
    "cataloging-in-publication",
    "library of congress",
    "isbn",
    "published by",
    "copyright",
)
_BACK_MATTER_TEXT_MARKERS = (
    "also by ",
    "other books by ",
    "about the author",
    "about the publisher",
)


class ParsedBookSection(BaseModel):
    """One readable EPUB spine document with its retrieval content role."""

    source_name: str
    text: str
    content_type: str = BODY_CONTENT_TYPE


class ParsedBook(BaseModel):
    source_path: str
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    sections: list[ParsedBookSection] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Retain the original parser text view for callers outside ingestion."""
        return "\n\n".join(section.text for section in self.sections)


def parse_epub(path: str | Path) -> ParsedBook:
    source = Path(path)
    try:
        return _parse_with_ebooklib(source)
    except Exception:
        return _parse_with_zip_fallback(source)


def _parse_with_ebooklib(source: Path) -> ParsedBook:
    book = epub.read_epub(str(source))
    title = _first_metadata(book, "DC", "title")
    authors = [value for value, _attrs in book.get_metadata("DC", "creator")]
    publisher = _first_metadata(book, "DC", "publisher")
    sections: list[ParsedBookSection] = []

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        if hasattr(item, "is_chapter") and not item.is_chapter():
            continue
        soup = BeautifulSoup(item.get_body_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            source_name = _item_source_name(item)
            sections.append(
                ParsedBookSection(
                    source_name=source_name,
                    text=text,
                    content_type=classify_epub_content_type(source_name, text),
                )
            )

    return ParsedBook(
        source_path=str(source),
        title=title,
        authors=authors,
        publisher=publisher,
        sections=sections,
    )


def _parse_with_zip_fallback(source: Path) -> ParsedBook:
    with ZipFile(source) as archive:
        opf_path = _find_opf_path(archive)
        opf_root = ElementTree.fromstring(archive.read(opf_path))
        metadata = _extract_opf_metadata(opf_root)
        spine_hrefs = _extract_spine_hrefs(opf_root)
        opf_dir = str(Path(opf_path).parent)
        sections: list[ParsedBookSection] = []

        for href in spine_hrefs:
            item_path = str(Path(opf_dir) / href) if opf_dir != "." else href
            try:
                content = archive.read(item_path)
            except KeyError:
                continue
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text("\n", strip=True)
            if text:
                sections.append(
                    ParsedBookSection(
                        source_name=href,
                        text=text,
                        content_type=classify_epub_content_type(href, text),
                    )
                )

    return ParsedBook(
        source_path=str(source),
        title=metadata.get("title"),
        authors=metadata.get("authors", []),
        publisher=metadata.get("publisher"),
        sections=sections,
    )


def classify_epub_content_type(source_name: str, text: str) -> str:
    """Classify clear publishing matter without treating ordinary prose as metadata.

    EPUB navigation and publisher pages often live in the same spine as the
    book body.  Keep their role alongside chunks so retrieval can exclude them
    by default while still making explicitly requested edition information
    searchable.
    """
    normalized_source = source_name.replace("\\", "/").casefold()
    normalized_text = " ".join(text.casefold().split())
    if any(marker in normalized_source for marker in _FRONT_MATTER_PATH_MARKERS):
        return FRONT_MATTER_CONTENT_TYPE
    if any(marker in normalized_source for marker in _BACK_MATTER_PATH_MARKERS):
        return BACK_MATTER_CONTENT_TYPE
    if any(marker in normalized_text for marker in _FRONT_MATTER_TEXT_MARKERS):
        return FRONT_MATTER_CONTENT_TYPE
    if any(marker in normalized_text for marker in _BACK_MATTER_TEXT_MARKERS):
        return BACK_MATTER_CONTENT_TYPE
    return BODY_CONTENT_TYPE


def _item_source_name(item: object) -> str:
    for attribute in ("get_name", "file_name", "get_id"):
        value = getattr(item, attribute, None)
        if callable(value):
            value = value()
        if isinstance(value, str) and value.strip():
            return value
    return "unknown"


def _find_opf_path(archive: ZipFile) -> str:
    try:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
    except KeyError:
        for name in archive.namelist():
            if name.endswith(".opf"):
                return name
        raise

    namespace = {"container": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile = container.find(".//container:rootfile", namespace)
    if rootfile is None:
        raise ValueError("EPUB container does not declare a rootfile")
    full_path = rootfile.attrib.get("full-path")
    if not full_path:
        raise ValueError("EPUB rootfile is missing full-path")
    return full_path


def _extract_opf_metadata(root: ElementTree.Element) -> dict[str, object]:
    namespace = {"dc": "http://purl.org/dc/elements/1.1/"}
    title = root.findtext(".//dc:title", namespaces=namespace)
    publisher = root.findtext(".//dc:publisher", namespaces=namespace)
    authors = [
        author.text.strip()
        for author in root.findall(".//dc:creator", namespace)
        if author.text and author.text.strip()
    ]
    return {"title": title, "authors": authors, "publisher": publisher}


def _extract_spine_hrefs(root: ElementTree.Element) -> list[str]:
    manifest = {
        item.attrib["id"]: item.attrib["href"]
        for item in root.findall(".//{*}manifest/{*}item")
        if "id" in item.attrib and "href" in item.attrib
    }
    hrefs: list[str] = []
    for itemref in root.findall(".//{*}spine/{*}itemref"):
        idref = itemref.attrib.get("idref")
        href = manifest.get(idref or "")
        if href and href.lower().endswith((".xhtml", ".html", ".htm")):
            hrefs.append(href)
    return hrefs


def _first_metadata(book: epub.EpubBook, namespace: str, name: str) -> str | None:
    values = book.get_metadata(namespace, name)
    if not values:
        return None
    return values[0][0]
