import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

GOLDEN_CORPUS_PATH = (
    REPO_ROOT / "tests/fixtures/evaluation/golden_retrieval_corpus.json"
)


class GoldenRetrievalCorpusTests(unittest.TestCase):
    def test_golden_corpus_uses_book_level_labels(self) -> None:
        """Verify the real-library benchmark starts with book-level labels.
        We do not want to pretend these are chunk-level gold labels yet; the
        corpus should be honest that it scores expected books first.
        """
        corpus = _load_corpus()

        self.assertEqual(corpus["label_granularity"], "book")
        self.assertEqual(corpus["benchmark"]["mode"], "live_search_expected_books")
        self.assertGreaterEqual(len(corpus["cases"]), 20)
        for case in corpus["cases"]:
            self.assertIn("query", case)
            self.assertIn("relevant_relative_paths", case)
            self.assertNotIn("results", case)

    def test_golden_corpus_expected_paths_match_known_local_epub_names(self) -> None:
        """Verify expected book labels match the local EPUB filenames.
        The EPUB files themselves stay ignored, but filename labels need to
        match the user's library exactly or live retrieval scoring will be
        confusing and noisy.
        """
        corpus = _load_corpus()
        known_relative_paths = {
            "All Quiet on the Western Front - Erich Maria Remarque.epub",
            "Alle Robotergeschichten - Asimov, Isaac.epub",
            "Baptism of Fire - Sapkowski, Andrzej.epub",
            "Blood of Elves - Andrzej Sapkowski.epub",
            "Children of Dune - Herbert, Frank.epub",
            "Complete Robot - Isaac Asimov.epub",
            "Designing Machine Learning Systems - Chip Huyen.epub",
            "Earthsea #01 - A Wizard of Earthsea - Ursula K. Le Guin.epub",
            "First They Killed My Father - Loung Ung.epub",
            "Forward the Foundation - Isaac Asimov.epub",
            "God Emperor of Dune - Frank Herbert.epub",
            "Never Split the Difference_ Negotiating As - Voss, Chris.epub",
            "Neuromancer - William Gibson.epub",
            "Paradise Lost - John Milton.epub",
            "Pol Pot - Philip Short.epub",
            "Sapkowski, Andrzej - Witcher 04 - The Towe - Sapkowski, Andrzej.epub",
            "Sapkowski, Andrzej - Witcher 05 - The Lady - Sapkowski, Andrzej.epub",
            "Shogun - James Clavell.epub",
            "The Handmaid's Tale - Margaret Atwood.epub",
            "The Last Wish_ Introducing the Witcher - Andrzej Sapkowski.epub",
            "The Left Hand of Darkness - Ursula Le Guin.epub",
            "The Naked Sun - Isaac Asimov.epub",
            "The Picture of Dorian Gray - Oscar Wilde.epub",
            "The Prince - Niccolo Machiavelli.epub",
            "The Republic - Plato.epub",
            "The Sickness Unto Death - Soren Kierkegaard.epub",
            "The Time of Contempt - Andrzej Sapkowski.epub",
            "The Tower of Swallows -- Sapkowski, Andrze - Unknown.epub",
            "The call of the wild - Jack London.epub",
            "Zen and the art of motorcycle maintenance - Robert Pirsig.epub",
            "[Roboter und Foundation 05] _ Die nackte S - Asimov, Isaac.epub",
        }

        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                for relative_path in case["relevant_relative_paths"]:
                    self.assertIn(relative_path, known_relative_paths)


def _load_corpus() -> dict:
    return json.loads(GOLDEN_CORPUS_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
