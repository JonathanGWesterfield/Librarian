import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
