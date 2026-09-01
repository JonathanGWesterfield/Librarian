import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from librarian_evaluation.answer import (
    AnswerCandidate,
    AnswerEvaluationCase,
    AnswerSource,
)
from librarian_evaluation.llm_judge import (
    LLMJudgeError,
    CodexJudge,
    StaticJudge,
    create_judge,
    evaluate_answers_with_llm_judge,
)
from librarian_evaluation import llm_judge


REPO_ROOT = Path(__file__).resolve().parents[2]


class LLMJudgeTests(unittest.TestCase):
    def test_evaluate_answers_with_llm_judge_parses_strict_semantic_verdict(self) -> None:
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
                    '{"evidence_verdict":"supported",'
                    '"citation_relevance":"all_relevant",'
                    '"missing_coverage":[],"unsupported_claims":[],'
                    '"reason":"Grounded and cited."}'
                ),
                provider="codex",
                model="gpt-5.6",
            ),
        )

        self.assertEqual(report.metric_type, "llm_judge")
        self.assertEqual(report.aggregate.case_count, 1)
        self.assertEqual(report.aggregate.mean_overall_score, 1.0)
        self.assertEqual(report.cases[0].evidence_verdict, "supported")
        self.assertEqual(report.cases[0].reason, "Grounded and cited.")
        self.assertEqual(report.mode, "enforcing")

    def test_judge_records_a_wrong_adversarial_verdict(self) -> None:
        """An opt-in semantic judge must expose disagreement with curated truth."""
        case = AnswerEvaluationCase(
            id="negation",
            question="Did Mara open the garden gate?",
            expected_judge_verdict="contradicted",
        )

        report = evaluate_answers_with_llm_judge(
            [case],
            {"negation": AnswerCandidate(answer="Mara opened it. [S1]", sources=[])},
            judge=StaticJudge(
                response=_semantic_response("supported"),
                provider="codex",
                model="gpt-5.6",
            ),
        )

        self.assertEqual(report.to_dict()["expectation_mismatch_count"], 1)
        self.assertEqual(report.cases[0].expected_judge_verdict, "contradicted")
        self.assertFalse(report.cases[0].expectation_met)

    def test_judge_records_a_matching_adversarial_verdict(self) -> None:
        """Matching curated semantic verdicts remain visible as successful checks."""
        case = AnswerEvaluationCase(
            id="negation",
            question="Did Mara open the garden gate?",
            expected_judge_verdict="contradicted",
        )

        report = evaluate_answers_with_llm_judge(
            [case],
            {"negation": AnswerCandidate(answer="Mara opened it. [S1]", sources=[])},
            judge=StaticJudge(
                response=_semantic_response("contradicted"),
                provider="codex",
                model="gpt-5.6",
            ),
        )

        self.assertEqual(report.to_dict()["expectation_mismatch_count"], 0)
        self.assertTrue(report.cases[0].expectation_met)

    def test_codex_judge_passes_the_requested_model_to_codex_exec(self) -> None:
        """Codex's judge subprocess must use --judge-model rather than config default."""
        completed = Mock(stdout='{"evidence_verdict":"supported"}')
        with patch("librarian_evaluation.llm_judge.subprocess.run", return_value=completed) as run:
            response = CodexJudge(model="gpt-5.6").judge("judge this answer")

        self.assertEqual(response, '{"evidence_verdict":"supported"}')
        self.assertEqual(
            run.call_args.args[0],
            ["codex", "exec", "--model", "gpt-5.6", "--ephemeral", "judge this answer"],
        )

    def test_enforcing_codex_failure_never_falls_back_to_ollama(self) -> None:
        """A failed quality gate must surface its Codex transport error directly."""
        case = AnswerEvaluationCase(id="sample", question="question")

        with self.assertRaisesRegex(LLMJudgeError, "primary failed"):
            evaluate_answers_with_llm_judge(
                [case],
                {"sample": AnswerCandidate(answer="answer", sources=[])},
                judge=_FailingJudge(),
            )

    def test_ollama_is_explicitly_advisory_and_can_still_validate_schema(self) -> None:
        """A local smoke judge reports a result without becoming a quality gate."""
        case = AnswerEvaluationCase(
            id="sample",
            question="question",
            expected_judge_verdict="contradicted",
        )
        report = evaluate_answers_with_llm_judge(
            [case],
            {"sample": AnswerCandidate(answer="answer", sources=[])},
            judge=StaticJudge(
                response=_semantic_response("supported"),
                provider="ollama",
                model="qwen2.5:1.5b",
            ),
            mode="advisory",
        )

        self.assertEqual(report.mode, "advisory")
        self.assertEqual(report.provider, "ollama")
        self.assertEqual(report.to_dict()["expectation_mismatch_count"], 1)

    def test_ollama_cannot_be_an_enforcing_semantic_judge(self) -> None:
        """A local model must never determine a semantic quality pass or failure."""
        with self.assertRaisesRegex(LLMJudgeError, "only a Codex judge"):
            evaluate_answers_with_llm_judge(
                [AnswerEvaluationCase(id="sample", question="question")],
                {"sample": AnswerCandidate(answer="answer", sources=[])},
                judge=StaticJudge(
                    response=_semantic_response("supported"),
                    provider="ollama",
                    model="qwen2.5:1.5b",
                ),
            )

    def test_llm_judge_rejects_a_response_that_is_not_the_semantic_schema(self) -> None:
        """A fuzzy evaluator must not silently accept an unstructured model reply."""
        with self.assertRaisesRegex(LLMJudgeError, "semantic verdict schema"):
            evaluate_answers_with_llm_judge(
                [AnswerEvaluationCase(id="sample", question="question")],
                {"sample": AnswerCandidate(answer="answer", sources=[])},
                judge=StaticJudge(
                    response='{"correctness": 1.0}',
                    provider="codex",
                    model="gpt-5.6",
                ),
            )

    def test_judge_prompt_uses_only_question_scope_answer_and_cited_passages(self) -> None:
        """Expected terms must not leak world knowledge into a semantic verdict."""
        case = AnswerEvaluationCase(
            id="scope",
            question="Who opened the gate?",
            scope={"book_title": "The Clockwork Garden"},
            expected_terms={"Mara", "Theo"},
            should_refuse=True,
        )
        candidate = AnswerCandidate(
            answer="Mara opened it. [S1]",
            sources=[
                AnswerSource(source_id="S1", text="Mara opened the gate."),
                AnswerSource(source_id="S2", text="Theo repaired the gate."),
            ],
        )

        prompt = llm_judge._build_judge_prompt(case, candidate)

        self.assertIn('"book_title": "The Clockwork Garden"', prompt)
        self.assertIn("Mara opened the gate.", prompt)
        self.assertNotIn("Theo repaired the gate.", prompt)
        self.assertNotIn("Expected concepts", prompt)
        self.assertNotIn("Should refuse", prompt)

    def test_configured_generation_provider_cannot_become_a_judge(self) -> None:
        """A gateway or local default cannot quietly replace the Codex gate."""
        with self.assertRaisesRegex(ValueError, "unsupported LLM judge provider"):
            create_judge(
                "configured",
                model="ignored",
                ollama_base_url="http://unused",
            )

    def test_adversarial_fixture_covers_the_known_semantic_failure_modes(self) -> None:
        """The judge corpus locks down the reviewer counterexamples as runnable data."""
        path = REPO_ROOT / "tests/fixtures/evaluation/groundedness_adversarial_cases.json"
        document = json.loads(path.read_text(encoding="utf-8"))

        expected = {
            "negation-contradiction": "contradicted",
            "reversed-relationship": "contradicted",
            "unsupported-causality": "insufficient",
            "broad-author-coverage": "insufficient",
        }
        self.assertEqual(
            {case["id"]: case["expected_judge_verdict"] for case in document["cases"]},
            expected,
        )
        self.assertTrue(all(case.get("scope") for case in document["cases"]))


class _FailingJudge:
    provider = "codex"
    model = "codex"

    def judge(self, _prompt: str) -> str:
        raise LLMJudgeError("primary failed")


def _semantic_response(verdict: str) -> str:
    return json.dumps(
        {
            "evidence_verdict": verdict,
            "citation_relevance": "all_relevant",
            "missing_coverage": [],
            "unsupported_claims": [],
            "reason": "Static semantic fixture verdict.",
        }
    )


if __name__ == "__main__":
    unittest.main()
