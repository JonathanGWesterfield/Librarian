import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from tests.ingestion.fixtures import (
    SAMPLE_AUTHORS,
    SAMPLE_EPUB,
    SAMPLE_PUBLISHER,
    SAMPLE_TEXT_FRAGMENTS,
    SAMPLE_TITLE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

try:
    from librarian_ingestion.epub import parse_epub
except ModuleNotFoundError as error:
    parse_epub = None
    PARSER_IMPORT_ERROR = error
else:
    PARSER_IMPORT_ERROR = None


@unittest.skipIf(
    parse_epub is None,
    f"EPUB parser dependencies are not installed: {PARSER_IMPORT_ERROR}",
)
class ParseEpubTests(unittest.TestCase):
    def test_parse_sample_epub_extracts_expected_metadata_and_text(self) -> None:
        """Verify EPUB parsing against the deterministic source-of-truth book.
        This protects metadata extraction and body text extraction, including
        the bug we fixed where chapter text was empty.
        """
        parsed = parse_epub(SAMPLE_EPUB)

        self.assertEqual(parsed.source_path, str(SAMPLE_EPUB))
        self.assertEqual(parsed.title, SAMPLE_TITLE)
        self.assertEqual(parsed.authors, SAMPLE_AUTHORS)
        self.assertEqual(parsed.publisher, SAMPLE_PUBLISHER)
        for fragment in SAMPLE_TEXT_FRAGMENTS:
            self.assertIn(fragment, parsed.text)

    def test_parse_epub_falls_back_when_manifest_references_missing_asset(self) -> None:
        """Verify malformed EPUB packages can still yield useful text.
        Some real EPUBs reference missing assets such as fonts; this test builds
        that shape and ensures the ZIP/XHTML fallback still extracts the book.
        """
        with TemporaryDirectory() as temp_dir:
            source_root = REPO_ROOT / "tests" / "fixtures" / "epub_source"
            malformed_epub = Path(temp_dir) / "missing-font.epub"
            opf = (source_root / "OEBPS" / "content.opf").read_text()
            opf = opf.replace(
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="missing-font" href="fonts/missing.otf" media-type="font/otf"/>\n'
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            )
            fixed_time = (2024, 1, 1, 0, 0, 0)
            entries = [
                ("mimetype", ZIP_STORED),
                ("META-INF/container.xml", ZIP_DEFLATED),
                ("OEBPS/chapter-1.xhtml", ZIP_DEFLATED),
                ("OEBPS/chapter-2.xhtml", ZIP_DEFLATED),
                ("OEBPS/nav.xhtml", ZIP_DEFLATED),
            ]
            with ZipFile(malformed_epub, "w") as archive:
                for name, compression in entries:
                    info = ZipInfo(name, fixed_time)
                    info.compress_type = compression
                    archive.writestr(info, (source_root / name).read_bytes())
                info = ZipInfo("OEBPS/content.opf", fixed_time)
                info.compress_type = ZIP_DEFLATED
                archive.writestr(info, opf.encode())

            parsed = parse_epub(malformed_epub)

        self.assertEqual(parsed.title, SAMPLE_TITLE)
        self.assertEqual(parsed.authors, SAMPLE_AUTHORS)
        self.assertIn("The clockwork garden woke at dawn.", parsed.text)


if __name__ == "__main__":
    unittest.main()
