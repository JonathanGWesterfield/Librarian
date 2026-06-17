from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from typing import Optional
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT
from ebooklib import epub
from pydantic import BaseModel, Field


class ParsedBook(BaseModel):
    source_path: str
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    publisher: Optional[str] = None
    text: str


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
    text_parts: list[str] = []

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        if hasattr(item, "is_chapter") and not item.is_chapter():
            continue
        soup = BeautifulSoup(item.get_body_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            text_parts.append(text)

    return ParsedBook(
        source_path=str(source),
        title=title,
        authors=authors,
        publisher=publisher,
        text="\n\n".join(text_parts),
    )


def _parse_with_zip_fallback(source: Path) -> ParsedBook:
    with ZipFile(source) as archive:
        opf_path = _find_opf_path(archive)
        opf_root = ElementTree.fromstring(archive.read(opf_path))
        metadata = _extract_opf_metadata(opf_root)
        spine_hrefs = _extract_spine_hrefs(opf_root)
        opf_dir = str(Path(opf_path).parent)
        text_parts: list[str] = []

        for href in spine_hrefs:
            item_path = str(Path(opf_dir) / href) if opf_dir != "." else href
            try:
                content = archive.read(item_path)
            except KeyError:
                continue
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text("\n", strip=True)
            if text:
                text_parts.append(text)

    return ParsedBook(
        source_path=str(source),
        title=metadata.get("title"),
        authors=metadata.get("authors", []),
        publisher=metadata.get("publisher"),
        text="\n\n".join(text_parts),
    )


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
