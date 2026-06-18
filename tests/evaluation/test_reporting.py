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
    evaluate_answer_cases,
)
from librarian_evaluation.reporting import (
    build_retrieval_report_document,
    render_evaluation_markdown,
)
from librarian_evaluation.llm_judge import StaticJudge, evaluate_answers_with_llm_judge
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
            answer_quality=evaluate_answer_cases(
                [
                    AnswerEvaluationCase(
                        id="answer",
                        question="answer question",
                        expected_terms={"grounded"},
                    )
                ],
                {
                    "answer": AnswerCandidate(
                        answer="A grounded answer [S1].",
                        sources=[AnswerSource(source_id="S1", text="grounded")],
                    )
                },
                generated_at="1970-01-01T00:00:00+00:00",
            ),
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
        self.assertIn("## Answer Quality", markdown)
        self.assertIn("## LLM Judge", markdown)
        self.assertIn("### Weakest Cases", markdown)
        self.assertIn("golden-library-retrieval", markdown)

    def test_render_evaluation_markdown_contains_run_metadata_when_present(self) -> None:
        """Verify runtime and git metadata are readable in Markdown reports.
        Dynamic run metadata is intentionally kept out of deterministic smoke
        report comparisons, but live reports and GitHub summaries should show
        elapsed time and the commit that produced the metrics.
        """
        report = evaluate_retrieval_cases(
            [
                RetrievalEvaluationCase(
                    id="good",
                    query="good query",
                    relevant_chunk_ids={"good:0"},
                )
            ],
            {
                "good": [
                    RetrievalResult(
                        chunk_id="good:0",
                        book_id="good",
                        relative_path="good.epub",
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
            run={
                "execution": {
                    "started_at": "1970-01-01T00:00:00+00:00",
                    "elapsed_seconds": 1.25,
                },
                "git": {
                    "short_commit": "abc1234",
                    "branch": "feature/test",
                    "dirty": False,
                },
            },
        ).to_dict()

        markdown = render_evaluation_markdown(document)

        self.assertIn("## Run Metadata", markdown)
        self.assertIn("abc1234", markdown)
        self.assertIn("1.2500s", markdown)

    def test_render_evaluation_markdown_contains_comparison_when_present(self) -> None:
        """Verify before/after metric deltas render for PR review.
        The comparison section is what makes run-over-run evaluation visible
        without asking reviewers to diff JSON by hand.
        """
        report = evaluate_retrieval_cases(
            [
                RetrievalEvaluationCase(
                    id="good",
                    query="good query",
                    relevant_chunk_ids={"good:0"},
                )
            ],
            {
                "good": [
                    RetrievalResult(
                        chunk_id="good:0",
                        book_id="good",
                        relative_path="good.epub",
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
        document["comparison"] = {
            "baseline": "main",
            "improved_count": 1,
            "regressed_count": 0,
            "unchanged_count": 0,
            "metrics": [
                {
                    "section": "retrieval",
                    "name": "overall_score",
                    "current": 0.8,
                    "baseline": 0.7,
                    "delta": 0.1,
                    "status": "improved",
                }
            ],
        }

        markdown = render_evaluation_markdown(document)

        self.assertIn("## Run Comparison", markdown)
        self.assertIn("overall_score", markdown)
        self.assertIn("+0.1000", markdown)

    def test_render_evaluation_markdown_contains_llm_judge_when_present(self) -> None:
        """Verify LLM-as-judge scores render next to deterministic metrics.
        The report should make the richer judge score visible without
        replacing the deterministic answer-quality section.
        """
        report = evaluate_retrieval_cases(
            [
                RetrievalEvaluationCase(
                    id="good",
                    query="good query",
                    relevant_chunk_ids={"good:0"},
                )
            ],
            {
                "good": [
                    RetrievalResult(
                        chunk_id="good:0",
                        book_id="good",
                        relative_path="good.epub",
                    )
                ]
            },
            k_values=[1],
            generated_at="1970-01-01T00:00:00+00:00",
        )
        llm_judge = evaluate_answers_with_llm_judge(
            [AnswerEvaluationCase(id="answer", question="answer question")],
            {"answer": AnswerCandidate(answer="answer", sources=[])},
            judge=StaticJudge(
                response=(
                    '{"correctness": 0.7, "completeness": 0.7, '
                    '"groundedness": 0.6, "citation_accuracy": 0.5, '
                    '"refusal_quality": 1.0, "usefulness": 0.7, '
                    '"overall_score": 0.7, "rationale": "Reasonable answer."}'
                ),
                provider="codex",
                model="codex",
            ),
        )
        document = build_retrieval_report_document(
            report,
            benchmark={"name": "unit-test", "mode": "static"},
            primary_k=1,
            llm_judge=llm_judge,
        ).to_dict()

        markdown = render_evaluation_markdown(document)

        self.assertIn("## LLM Judge", markdown)
        self.assertIn("Reasonable answer.", markdown)
        self.assertIn("Overall judge score", markdown)


if __name__ == "__main__":
    unittest.main()
