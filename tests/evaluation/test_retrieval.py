import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_evaluation.retrieval import (
    RetrievalEvaluationCase,
    RetrievalResult,
    evaluate_retrieval_case,
    evaluate_retrieval_cases,
)
from librarian_search.search import SearchResult


class RetrievalEvaluationTests(unittest.TestCase):
    def test_evaluate_retrieval_case_scores_ranked_results(self) -> None:
        """Verify the basic retrieval metrics for one benchmark query.
        This test locks down the first automatic evaluation layer: the case
        declares expected evidence, ranked search results are scored, and we
        calculate hit, precision, recall, and reciprocal rank.
        """
        case = RetrievalEvaluationCase(
            id="war-brutality",
            query="How brutal and terrible is war?",
            relevant_chunk_ids={"all-quiet:4", "all-quiet:8"},
        )
        ranked_results = [
            RetrievalResult(
                chunk_id="other-book:0",
                book_id="other-book",
                relative_path="Other Book.epub",
            ),
            RetrievalResult(
                chunk_id="all-quiet:4",
                book_id="all-quiet",
                relative_path="All Quiet on the Western Front.epub",
            ),
            RetrievalResult(
                chunk_id="all-quiet:8",
                book_id="all-quiet",
                relative_path="All Quiet on the Western Front.epub",
            ),
        ]

        metrics = evaluate_retrieval_case(case, ranked_results, k_values=[1, 2, 3])

        self.assertFalse(metrics.hit_at_k[1])
        self.assertTrue(metrics.hit_at_k[2])
        self.assertEqual(metrics.precision_at_k[1], 0.0)
        self.assertEqual(metrics.precision_at_k[2], 0.5)
        self.assertEqual(metrics.recall_at_k[2], 0.5)
        self.assertEqual(metrics.recall_at_k[3], 1.0)
        self.assertEqual(metrics.reciprocal_rank, 0.5)

    def test_evaluate_retrieval_cases_aggregates_report_metrics(self) -> None:
        """Verify multiple cases roll up into one report.
        This report is the north-star shape we will grow: individual cases stay
        inspectable, while aggregate metrics give us a fast read on whether a
        retrieval change improved or regressed the system.
        """
        cases = [
            RetrievalEvaluationCase(
                id="case-1",
                query="clockwork gardens",
                relevant_chunk_ids={"book-a:0"},
            ),
            RetrievalEvaluationCase(
                id="case-2",
                query="moonlit oceans",
                relevant_relative_paths={"ocean.epub"},
            ),
        ]
        ranked_results_by_case = {
            "case-1": [
                RetrievalResult(
                    chunk_id="book-a:0",
                    book_id="book-a",
                    relative_path="garden.epub",
                )
            ],
            "case-2": [
                RetrievalResult(
                    chunk_id="book-b:0",
                    book_id="book-b",
                    relative_path="wrong.epub",
                ),
                RetrievalResult(
                    chunk_id="book-c:0",
                    book_id="book-c",
                    relative_path="ocean.epub",
                ),
            ],
        }

        report = evaluate_retrieval_cases(
            cases,
            ranked_results_by_case,
            k_values=[1, 2],
        )

        self.assertEqual(report.metric_type, "retrieval")
        self.assertEqual(report.aggregate.case_count, 2)
        self.assertEqual(report.aggregate.hit_rate_at_k[1], 0.5)
        self.assertEqual(report.aggregate.hit_rate_at_k[2], 1.0)
        self.assertEqual(report.aggregate.mean_precision_at_k[1], 0.5)
        self.assertEqual(report.aggregate.mean_recall_at_k[2], 1.0)
        self.assertEqual(report.aggregate.mean_reciprocal_rank, 0.75)
        self.assertEqual(len(report.to_dict()["cases"]), 2)

    def test_evaluate_retrieval_accepts_search_results(self) -> None:
        """Verify the evaluator can consume production search results.
        Search returns `SearchResult` objects today, so the evaluator accepts
        that shape directly instead of requiring callers to copy every result
        into an evaluation-specific record first.
        """
        case = RetrievalEvaluationCase(
            id="sample",
            query="clockwork garden",
            relevant_book_ids={"book-hash"},
        )
        search_result = SearchResult(
            score=0.99,
            chunk_id="book-hash:0",
            book_id="book-hash",
            relative_path="sample.epub",
            title="Sample Book",
            authors=["Test Author"],
            publisher="Fixture Press",
            chunk_index=0,
            text="The clockwork garden woke at dawn.",
            embedding_provider="ollama",
            embedding_model="all-minilm",
            dimensions=2,
        )

        metrics = evaluate_retrieval_case(case, [search_result], k_values=[1])

        self.assertTrue(metrics.hit_at_k[1])
        self.assertEqual(metrics.precision_at_k[1], 1.0)
        self.assertEqual(metrics.recall_at_k[1], 1.0)


if __name__ == "__main__":
    unittest.main()
