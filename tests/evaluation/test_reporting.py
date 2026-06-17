import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_evaluation.reporting import (
    build_retrieval_report_document,
    render_evaluation_markdown,
)
from librarian_evaluation.retrieval import (
    RetrievalEvaluationCase,
    RetrievalResult,
    evaluate_retrieval_cases,
)


class RetrievalReportingTests(unittest.TestCase):
    def test_build_retrieval_report_document_synthesizes_actionable_summary(self) -> None:
        """Verify raw metrics become a readable report summary.
        The report should tell a human what happened overall and which cases
        need attention, not only expose raw metric dictionaries.
        """
        report = evaluate_retrieval_cases(
            [
                RetrievalEvaluationCase(
                    id="good",
                    query="good query",
                    relevant_chunk_ids={"good:0"},
                ),
                RetrievalEvaluationCase(
                    id="miss",
                    query="missed query",
                    relevant_chunk_ids={"target:0"},
                ),
            ],
            {
                "good": [
                    RetrievalResult(
                        chunk_id="good:0",
                        book_id="good",
                        relative_path="good.epub",
                    )
                ],
                "miss": [
                    RetrievalResult(
                        chunk_id="noise:0",
                        book_id="noise",
                        relative_path="noise.epub",
                    )
                ],
            },
            k_values=[1],
            generated_at="1970-01-01T00:00:00+00:00",
        )

        document = build_retrieval_report_document(
            report,
            benchmark={"name": "unit-test"},
            primary_k=1,
        ).to_dict()

        self.assertEqual(document["report_type"], "retrieval_evaluation")
        self.assertIn("Hit@1 is 50%", document["summary"]["headline"])
        self.assertEqual(document["summary"]["overall_score"], 0.5)
        self.assertEqual(
            document["summary"]["weakest_cases"][0]["case_id"],
            "miss",
        )
        self.assertIn(
            "No relevant evidence appeared",
            document["summary"]["weakest_cases"][0]["reason"],
        )

    def test_render_evaluation_markdown_contains_human_readable_sections(self) -> None:
        """Verify the Checks-facing report is organized by evaluation area.
        The GitHub summary should be readable by a human reviewer, with
        separate sections for embeddings, the golden corpus, and retrieval
        metrics instead of requiring someone to mentally parse raw JSON.
        """
        report = evaluate_retrieval_cases(
            [
                RetrievalEvaluationCase(
                    id="miss",
                    query="missed query",
                    relevant_chunk_ids={"target:0"},
                )
            ],
            {
                "miss": [
                    RetrievalResult(
                        chunk_id="noise:0",
                        book_id="noise",
                        relative_path="noise.epub",
                    )
                ]
            },
            k_values=[1],
            generated_at="1970-01-01T00:00:00+00:00",
        )
        document = build_retrieval_report_document(
            report,
            benchmark={"name": "unit-test", "mode": "static"},
            primary_k=1,
        ).to_dict()

        markdown = render_evaluation_markdown(
            document,
            golden_corpus={
                "benchmark": {
                    "name": "golden-library-retrieval",
                    "mode": "live_search_expected_books",
                },
                "label_granularity": "book",
                "primary_k": 10,
                "cases": [
                    {
                        "id": "war-brutality-all-quiet",
                        "relevant_relative_paths": ["All Quiet.epub"],
                    }
                ],
            },
        )

        self.assertIn("## Embeddings", markdown)
        self.assertIn("## Golden Corpus", markdown)
        self.assertIn("## Retrieval Metrics", markdown)
        self.assertIn("### Weakest Cases", markdown)
        self.assertIn("golden-library-retrieval", markdown)


if __name__ == "__main__":
    unittest.main()
