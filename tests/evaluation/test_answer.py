import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_evaluation.answer import (
    AnswerCandidate,
    AnswerEvaluationCase,
    AnswerSource,
    evaluate_answer_case,
    evaluate_answer_cases,
)


class AnswerEvaluationTests(unittest.TestCase):
    def test_evaluate_answer_case_scores_grounded_cited_answer(self) -> None:
        """Verify a grounded answer earns full deterministic rubric scores.
        This locks down the first answer-quality layer: expected concepts are
        present, citations are valid, and cited text supports those concepts.
        """
        case = AnswerEvaluationCase(
            id="war",
            question="How brutal and terrible is war?",
            expected_terms={"fear", "death", "trauma"},
        )
        candidate = AnswerCandidate(
            answer="War is shown through fear, death, and trauma [S1].",
            sources=[
                AnswerSource(
                    source_id="S1",
                    relative_path="all-quiet.epub",
                    text="The passage describes fear, death, and trauma.",
                )
            ],
        )

        metrics = evaluate_answer_case(case, candidate)

        self.assertEqual(metrics.correctness, 1.0)
        self.assertEqual(metrics.completeness, 1.0)
        self.assertEqual(metrics.groundedness, 1.0)
        self.assertEqual(metrics.citation_accuracy, 1.0)
        self.assertEqual(metrics.overall_score, 1.0)

    def test_evaluate_answer_case_penalizes_missing_citations(self) -> None:
        """Verify uncited answers are penalized even when terms are present.
        This keeps fluently correct-looking answers from passing unless they
        preserve source attribution, which is central to this app.
        """
        case = AnswerEvaluationCase(
            id="uncited",
            question="What does the source say?",
            expected_terms={"clockwork", "garden"},
        )
        candidate = AnswerCandidate(
            answer="The answer mentions a clockwork garden.",
            sources=[
                AnswerSource(
                    source_id="S1",
                    relative_path="sample.epub",
                    text="The clockwork garden woke at dawn.",
                )
            ],
        )

        metrics = evaluate_answer_case(case, candidate)

        self.assertEqual(metrics.correctness, 1.0)
        self.assertEqual(metrics.citation_accuracy, 0.0)
        self.assertLess(metrics.groundedness, 1.0)
        self.assertIn("Answer did not cite any sources.", metrics.findings)

    def test_evaluate_answer_cases_aggregates_scores(self) -> None:
        """Verify answer-quality cases roll up into aggregate scores.
        The report layer needs aggregate metrics so we can track answer quality
        over time separately from retrieval quality.
        """
        cases = [
            AnswerEvaluationCase(
                id="good",
                question="good question",
                expected_terms={"grounded"},
            ),
            AnswerEvaluationCase(
                id="refusal",
                question="unknown question",
                should_refuse=True,
            ),
        ]
        report = evaluate_answer_cases(
            cases,
            {
                "good": AnswerCandidate(
                    answer="A grounded answer [S1].",
                    sources=[AnswerSource(source_id="S1", text="grounded")],
                ),
                "refusal": AnswerCandidate(
                    answer="The local library context is insufficient.",
                    sources=[],
                ),
            },
            generated_at="1970-01-01T00:00:00+00:00",
        )

        self.assertEqual(report.metric_type, "answer_quality")
        self.assertEqual(report.aggregate.case_count, 2)
        self.assertEqual(report.aggregate.mean_refusal_quality, 1.0)
        self.assertGreater(report.aggregate.mean_overall_score, 0.9)


if __name__ == "__main__":
    unittest.main()
