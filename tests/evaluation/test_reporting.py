import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_evaluation.reporting import build_retrieval_report_document
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


if __name__ == "__main__":
    unittest.main()
