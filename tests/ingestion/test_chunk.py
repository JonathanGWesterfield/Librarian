import sys
import unittest
from pathlib import Path

from tests.ingestion.fixtures import SAMPLE_EPUB, SAMPLE_TEXT_FRAGMENTS

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_ingestion.chunk import chunk_text, clean_text, estimate_tokens
from librarian_ingestion.epub import parse_epub


class CleanTextTests(unittest.TestCase):
    def test_clean_text_normalizes_whitespace_and_preserves_paragraphs(self) -> None:
        """Verify cleanup removes noisy spacing without flattening structure.
        Paragraph boundaries are useful retrieval context, so the cleaner should
        normalize text while preserving those breaks.
        """
        text = "  First   paragraph.\n\n\nSecond\tparagraph.  "

        self.assertEqual(clean_text(text), "First paragraph.\n\nSecond paragraph.")


class ChunkTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_book = parse_epub(SAMPLE_EPUB)

    def test_chunk_text_creates_ordered_chunks_with_estimates(self) -> None:
        """Verify chunking produces ordered, non-empty records.
        Embedding and citation layers will depend on stable chunk indexes,
        character counts, and approximate token counts.
        """
        text = "Alpha sentence. " * 80

        chunks = chunk_text(text, target_size=120, overlap=20)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        self.assertTrue(all(chunk.character_count > 0 for chunk in chunks))
        self.assertTrue(all(chunk.token_estimate > 0 for chunk in chunks))

    def test_chunk_text_rejects_invalid_sizes(self) -> None:
        """Verify invalid chunking settings fail immediately.
        A target size and overlap that cannot make forward progress would cause
        bad chunks or loops, so the chunker should reject it early.
        """
        with self.assertRaises(ValueError):
            chunk_text("text", target_size=10, overlap=10)

    def test_estimate_tokens_handles_empty_text(self) -> None:
        """Verify empty text has a zero token estimate.
        This avoids treating missing content as a meaningful chunk during later
        embedding or prompt-budget calculations.
        """
        self.assertEqual(estimate_tokens(""), 0)

    def test_sample_epub_chunks_preserve_source_text(self) -> None:
        """Verify chunking behavior against the source-of-truth EPUB fixture.
        This exercises real parsed book text and confirms small chunks still
        keep ordered indexes, useful sizes, and all expected source fragments.
        """
        chunks = chunk_text(self.sample_book.text, target_size=90, overlap=20)
        joined_chunks = "\n".join(chunk.text for chunk in chunks)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        self.assertTrue(all(chunk.character_count <= 110 for chunk in chunks))
        for fragment in SAMPLE_TEXT_FRAGMENTS:
            self.assertIn(fragment, joined_chunks)


if __name__ == "__main__":
    unittest.main()
