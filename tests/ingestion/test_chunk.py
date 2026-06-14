import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.chunk import chunk_text, clean_text, estimate_tokens


class CleanTextTests(unittest.TestCase):
    def test_clean_text_normalizes_whitespace_and_preserves_paragraphs(self) -> None:
        """Verify cleanup removes noisy spacing without flattening structure.
        Paragraph boundaries are useful retrieval context, so the cleaner should
        normalize text while preserving those breaks.
        """
        text = "  First   paragraph.\n\n\nSecond\tparagraph.  "

        self.assertEqual(clean_text(text), "First paragraph.\n\nSecond paragraph.")


class ChunkTextTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
