import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.chunk import chunk_text, clean_text, estimate_tokens


class CleanTextTests(unittest.TestCase):
    def test_clean_text_normalizes_whitespace_and_preserves_paragraphs(self) -> None:
        text = "  First   paragraph.\n\n\nSecond\tparagraph.  "

        self.assertEqual(clean_text(text), "First paragraph.\n\nSecond paragraph.")


class ChunkTextTests(unittest.TestCase):
    def test_chunk_text_creates_ordered_chunks_with_estimates(self) -> None:
        text = "Alpha sentence. " * 80

        chunks = chunk_text(text, target_size=120, overlap=20)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        self.assertTrue(all(chunk.character_count > 0 for chunk in chunks))
        self.assertTrue(all(chunk.token_estimate > 0 for chunk in chunks))

    def test_chunk_text_rejects_invalid_sizes(self) -> None:
        with self.assertRaises(ValueError):
            chunk_text("text", target_size=10, overlap=10)

    def test_estimate_tokens_handles_empty_text(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)


if __name__ == "__main__":
    unittest.main()

