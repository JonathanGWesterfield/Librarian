import unittest

from librarian_evaluation.answer import (
    AnswerCandidate,
    AnswerEvaluationCase,
    AnswerSource,
)
from librarian_evaluation.llm_judge import (
    LLMJudgeError,
    StaticJudge,
    evaluate_answers_with_llm_judge,
)


class LLMJudgeTests(unittest.TestCase):
    def test_evaluate_answers_with_llm_judge_parses_structured_scores(self) -> None:
        """Verify an LLM judge response becomes aggregate answer metrics.
        The real providers are nondeterministic and external, so this test
        locks down the structured JSON contract that Codex and Ollama must
        satisfy.
        """
        case = AnswerEvaluationCase(
            id="war",
            question="How brutal and terrible is war?",
            expected_terms={"fear", "death"},
        )
        candidate = AnswerCandidate(
            answer="War is described through fear and death [S1].",
            sources=[AnswerSource(source_id="S1", text="fear and death")],
        )

        report = evaluate_answers_with_llm_judge(
            [case],
            {"war": candidate},
            judge=StaticJudge(
                response=(
                    '{"correctness": 0.9, "completeness": 0.8, '
                    '"groundedness": 1.0, "citation_accuracy": 1.0, '
                    '"refusal_quality": 1.0, "usefulness": 0.9, '
                    '"overall_score": 0.92, "rationale": "Grounded and cited."}'
                )
            ),
        )

        self.assertEqual(report.metric_type, "llm_judge")
        self.assertEqual(report.aggregate.case_count, 1)
        self.assertEqual(report.aggregate.mean_overall_score, 0.92)
        self.assertEqual(report.cases[0].rationale, "Grounded and cited.")

    def test_evaluate_answers_with_llm_judge_uses_fallback_provider(self) -> None:
        """Verify Ollama can take over when the primary Codex-style judge fails.
        This keeps the local evaluation workflow useful on machines where
        Codex is unavailable, while still preferring Codex by default.
        """
        case = AnswerEvaluationCase(id="sample", question="question")

        report = evaluate_answers_with_llm_judge(
            [case],
            {"sample": AnswerCandidate(answer="answer", sources=[])},
            judge=_FailingJudge(),
            fallback_judge=StaticJudge(
                response=(
                    '{"correctness": 0.5, "completeness": 0.5, '
                    '"groundedness": 0.5, "citation_accuracy": 0.5, '
                    '"refusal_quality": 0.5, "usefulness": 0.5, '
                    '"overall_score": 0.5, "rationale": "Fallback score."}'
                ),
                provider="ollama",
                model="llama3.2:3b",
            ),
        )

        self.assertTrue(report.fallback_used)
        self.assertEqual(report.provider, "ollama")
        self.assertEqual(report.model, "llama3.2:3b")


class _FailingJudge:
    provider = "codex"
    model = "codex"

    def judge(self, _prompt: str) -> str:
        raise LLMJudgeError("primary failed")


if __name__ == "__main__":
    unittest.main()
