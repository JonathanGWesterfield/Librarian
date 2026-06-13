from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub
from pydantic import BaseModel


class ParsedBook(BaseModel):
    source_path: str
    title: str | None = None
    authors: list[str] = []
    text: str


def parse_epub(path: str | Path) -> ParsedBook:
    source = Path(path)
    book = epub.read_epub(str(source))
    title = _first_metadata(book, "DC", "title")
    authors = [value for value, _attrs in book.get_metadata("DC", "creator")]
    text_parts: list[str] = []

    for item in book.get_items_of_type(epub.EpubHtml):
        soup = BeautifulSoup(item.get_body_content(), "html.parser")
        text = soup.get_text("\n", strip=True)
        if text:
            text_parts.append(text)

    return ParsedBook(
        source_path=str(source),
        title=title,
        authors=authors,
        text="\n\n".join(text_parts),
    )


def _first_metadata(book: epub.EpubBook, namespace: str, name: str) -> str | None:
    values = book.get_metadata(namespace, name)
    if not values:
        return None
    return values[0][0]

