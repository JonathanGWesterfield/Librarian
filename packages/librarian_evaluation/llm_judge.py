from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Literal, Protocol
from urllib import error, request

from librarian_chat.generation import (
    ChatMessage,
    GenerationError,
    Generator,
    create_configured_generator,
)
from librarian_evaluation.answer import AnswerCandidate, AnswerEvaluationCase


class LLMJudgeError(RuntimeError):
    pass


class LLMJudge(Protocol):
    provider: str
    model: str

    def judge(self, prompt: str) -> str:
        ...


EvidenceVerdict = Literal["supported", "contradicted", "insufficient"]
CitationRelevance = Literal[
    "all_relevant", "partially_relevant", "irrelevant", "not_applicable"
]


@dataclass(frozen=True)
class SemanticJudgeResult:
    """Strict, source-only semantic verdict returned by an LLM judge."""

    evidence_verdict: EvidenceVerdict
    citation_relevance: CitationRelevance
    missing_coverage: list[str]
    unsupported_claims: list[str]
    reason: str


@dataclass(frozen=True)
class LLMJudgeCaseMetrics:
    case_id: str
    question: str
    provider: str
    model: str
    correctness: float
    completeness: float
    groundedness: float
    citation_accuracy: float
    refusal_quality: float
    usefulness: float
    overall_score: float
    evidence_verdict: EvidenceVerdict
    citation_relevance: CitationRelevance
    missing_coverage: list[str]
    unsupported_claims: list[str]
    reason: str
    expected_judge_verdict: EvidenceVerdict | None
    expectation_met: bool | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LLMJudgeAggregateMetrics:
    case_count: int
    mean_correctness: float
    mean_completeness: float
    mean_groundedness: float
    mean_citation_accuracy: float
    mean_refusal_quality: float
    mean_usefulness: float
    mean_overall_score: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LLMJudgeReport:
    provider: str
    model: str
    fallback_provider: str | None
    fallback_used: bool
    metric_type: str
    aggregate: LLMJudgeAggregateMetrics
    cases: list[LLMJudgeCaseMetrics]

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "fallback_provider": self.fallback_provider,
            "fallback_used": self.fallback_used,
            "metric_type": self.metric_type,
            "aggregate": self.aggregate.to_dict(),
            "expectation_case_count": sum(
                case.expected_judge_verdict is not None for case in self.cases
            ),
            "expectation_mismatch_count": sum(
                case.expectation_met is False for case in self.cases
            ),
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class StaticJudge:
    response: str
    provider: str = "static"
    model: str = "static"

    def judge(self, prompt: str) -> str:
        return self.response


@dataclass(frozen=True)
class CodexJudge:
    model: str = "codex"
    timeout_seconds: float = 240.0
    provider: str = "codex"

    def judge(self, prompt: str) -> str:
        try:
            completed = subprocess.run(
                ["codex", "exec", "--model", self.model, "--ephemeral", prompt],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LLMJudgeError(f"could not run Codex judge: {exc}") from exc
        return completed.stdout.strip()


@dataclass(frozen=True)
class ConfiguredGeneratorJudge:
    """Opt-in judge that uses the existing JSON-configured generation provider."""

    generator: Generator

    @property
    def provider(self) -> str:
        return self.generator.provider

    @property
    def model(self) -> str:
        return self.generator.model

    def judge(self, prompt: str) -> str:
        try:
            return self.generator.generate(
                [
                    ChatMessage(
                        role="system",
                        content=(
                            "You are a strict source-only RAG evaluator. Return only "
                            "the requested JSON object."
                        ),
                    ),
                    ChatMessage(role="user", content=prompt),
                ],
                response_format="json",
            )
        except GenerationError as exc:
            raise LLMJudgeError(f"configured judge failed: {exc}") from exc


@dataclass(frozen=True)
class OllamaJudge:
    model: str
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 240.0
    provider: str = "ollama"

    def judge(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a strict RAG answer-quality judge.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            }
        ).encode("utf-8")
        endpoint = f"{self.base_url.rstrip('/')}/api/chat"
        http_request = request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise LLMJudgeError(f"could not reach Ollama at {endpoint}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMJudgeError("Ollama judge returned invalid JSON") from exc

        message = response_payload.get("message")
        if not isinstance(message, dict):
            raise LLMJudgeError("Ollama judge response did not include a message")
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMJudgeError("Ollama judge response message did not include content")
        return content.strip()


def create_judge(
    provider: str,
    *,
    model: str,
    ollama_base_url: str,
) -> LLMJudge:
    normalized = provider.strip().casefold()
    if normalized == "configured":
        return ConfiguredGeneratorJudge(create_configured_generator())
    if normalized == "codex":
        return CodexJudge(model=model or "codex")
    if normalized == "ollama":
        return OllamaJudge(model=model, base_url=ollama_base_url)
    raise ValueError(f"unsupported LLM judge provider: {provider}")


def evaluate_answers_with_llm_judge(
    cases: list[AnswerEvaluationCase],
    candidates_by_case: dict[str, AnswerCandidate],
    *,
    judge: LLMJudge,
    fallback_judge: LLMJudge | None = None,
) -> LLMJudgeReport:
    active_judge = judge
    fallback_used = False
    case_metrics: list[LLMJudgeCaseMetrics] = []

    for case in cases:
        candidate = candidates_by_case.get(case.id, AnswerCandidate(answer="", sources=[]))
        prompt = _build_judge_prompt(case, candidate)
        try:
            raw_response = active_judge.judge(prompt)
        except LLMJudgeError:
            if fallback_judge is None:
                raise
            active_judge = fallback_judge
            fallback_used = True
            raw_response = active_judge.judge(prompt)
        case_metrics.append(
            _case_metrics_from_response(
                case,
                candidate,
                raw_response,
                provider=active_judge.provider,
                model=active_judge.model,
            )
        )

    return LLMJudgeReport(
        provider=active_judge.provider,
        model=active_judge.model,
        fallback_provider=fallback_judge.provider if fallback_judge else None,
        fallback_used=fallback_used,
        metric_type="llm_judge",
        aggregate=_aggregate(case_metrics),
        cases=case_metrics,
    )


def _build_judge_prompt(
    case: AnswerEvaluationCase,
    candidate: AnswerCandidate,
) -> str:
    cited_ids = set(_citation_ids(candidate.answer))
    cited_sources = [
        source for source in candidate.sources if source.source_id in cited_ids
    ]
    sources = "\n\n".join(
        f"[{source.source_id}] {source.relative_path or 'unknown source'}\n{source.text}"
        for source in cited_sources
    )
    scope = (
        json.dumps(case.scope, sort_keys=True)
        if case.scope
        else "No explicit scope."
    )
    return (
        "Evaluate a retrieval-augmented book-assistant answer using ONLY the "
        "question, scope, answer, and cited passages below. Do not use training "
        "knowledge, assumptions about the book, or uncited passages.\n\n"
        "Return exactly one JSON object with exactly these keys:\n"
        '{"evidence_verdict":"supported|contradicted|insufficient",'
        '"citation_relevance":"all_relevant|partially_relevant|irrelevant|not_applicable",'
        '"missing_coverage":["short missing point"],'
        '"unsupported_claims":["short unsupported claim"],'
        '"reason":"concise source-only explanation"}\n\n'
        "Use supported only when every material answer claim follows from the "
        "cited passages. Use contradicted when a cited passage conflicts with a "
        "claim. Use insufficient when the passages neither support nor contradict "
        "a material claim. `not_applicable` is only for an answer with no citations.\n\n"
        f"Question:\n{case.question}\n\n"
        f"Scope:\n{scope}\n\n"
        f"Answer:\n{candidate.answer}\n\n"
        f"Cited passages:\n{sources or 'No cited passages provided.'}"
    )


def _case_metrics_from_response(
    case: AnswerEvaluationCase,
    candidate: AnswerCandidate,
    response: str,
    *,
    provider: str,
    model: str,
) -> LLMJudgeCaseMetrics:
    payload = _extract_json_object(response)
    semantic = _semantic_result_from_payload(payload)
    correctness, completeness, groundedness, citation_accuracy, refusal_quality, usefulness = (
        _scores_from_semantic_result(case, candidate, semantic)
    )
    overall_score = _score(
        (
            correctness
            + completeness
            + groundedness
            + citation_accuracy
            + refusal_quality
            + usefulness
        )
        / 6
    )
    expected_judge_verdict = _expected_judge_verdict(case)
    return LLMJudgeCaseMetrics(
        case_id=case.id,
        question=case.question,
        provider=provider,
        model=model,
        correctness=correctness,
        completeness=completeness,
        groundedness=groundedness,
        citation_accuracy=citation_accuracy,
        refusal_quality=refusal_quality,
        usefulness=usefulness,
        overall_score=overall_score,
        evidence_verdict=semantic.evidence_verdict,
        citation_relevance=semantic.citation_relevance,
        missing_coverage=semantic.missing_coverage,
        unsupported_claims=semantic.unsupported_claims,
        reason=semantic.reason,
        expected_judge_verdict=expected_judge_verdict,
        expectation_met=(
            semantic.evidence_verdict == expected_judge_verdict
            if expected_judge_verdict is not None
            else None
        ),
    )


def _expected_judge_verdict(
    case: AnswerEvaluationCase,
) -> EvidenceVerdict | None:
    expected = case.expected_judge_verdict
    if expected is None:
        return None
    if expected not in {"supported", "contradicted", "insufficient"}:
        raise LLMJudgeError(
            f"case {case.id!r} has invalid expected_judge_verdict: {expected!r}"
        )
    return expected


def _semantic_result_from_payload(payload: dict[str, object]) -> SemanticJudgeResult:
    expected_keys = {
        "evidence_verdict",
        "citation_relevance",
        "missing_coverage",
        "unsupported_claims",
        "reason",
    }
    if set(payload) != expected_keys:
        raise LLMJudgeError(
            "LLM judge response must contain exactly the semantic verdict schema keys"
        )
    verdict = payload["evidence_verdict"]
    relevance = payload["citation_relevance"]
    if not isinstance(verdict, str) or verdict not in {
        "supported",
        "contradicted",
        "insufficient",
    }:
        raise LLMJudgeError("LLM judge returned an invalid evidence_verdict")
    if not isinstance(relevance, str) or relevance not in {
        "all_relevant",
        "partially_relevant",
        "irrelevant",
        "not_applicable",
    }:
        raise LLMJudgeError("LLM judge returned an invalid citation_relevance")
    missing_coverage = _string_list(
        payload["missing_coverage"], "missing_coverage"
    )
    unsupported_claims = _string_list(
        payload["unsupported_claims"], "unsupported_claims"
    )
    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise LLMJudgeError("LLM judge reason must be a non-empty string")
    return SemanticJudgeResult(
        evidence_verdict=verdict,
        citation_relevance=relevance,
        missing_coverage=missing_coverage,
        unsupported_claims=unsupported_claims,
        reason=reason.strip(),
    )


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise LLMJudgeError(
            f"LLM judge {field_name} must be a list of non-empty strings"
        )
    return [item.strip() for item in value]


def _scores_from_semantic_result(
    case: AnswerEvaluationCase,
    candidate: AnswerCandidate,
    result: SemanticJudgeResult,
) -> tuple[float, float, float, float, float, float]:
    supported = result.evidence_verdict == "supported"
    insufficient = result.evidence_verdict == "insufficient"
    correctness = 1.0 if supported or (insufficient and case.should_refuse) else 0.0
    completeness = 1.0 if not result.missing_coverage else 0.0
    groundedness = 1.0 if supported and not result.unsupported_claims else 0.0
    citation_accuracy = {
        "all_relevant": 1.0,
        "partially_relevant": 0.5,
        "irrelevant": 0.0,
        "not_applicable": 1.0 if not _citation_ids(candidate.answer) else 0.0,
    }[result.citation_relevance]
    refusal_quality = 1.0 if not case.should_refuse else float(insufficient)
    usefulness = _score(
        (correctness + completeness + groundedness + citation_accuracy) / 4
    )
    return (
        _score(correctness),
        _score(completeness),
        _score(groundedness),
        _score(citation_accuracy),
        _score(refusal_quality),
        usefulness,
    )


def _citation_ids(answer: str) -> list[str]:
    return re.findall(r"\[(S\d+)\]", answer)


def _extract_json_object(response: str) -> dict[str, object]:
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}")
        if start < 0 or end < start:
            raise LLMJudgeError("LLM judge did not return a JSON object")
        try:
            parsed = json.loads(response[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMJudgeError("LLM judge returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMJudgeError("LLM judge response JSON was not an object")
    return parsed


def _aggregate(cases: list[LLMJudgeCaseMetrics]) -> LLMJudgeAggregateMetrics:
    if not cases:
        return LLMJudgeAggregateMetrics(
            case_count=0,
            mean_correctness=0.0,
            mean_completeness=0.0,
            mean_groundedness=0.0,
            mean_citation_accuracy=0.0,
            mean_refusal_quality=0.0,
            mean_usefulness=0.0,
            mean_overall_score=0.0,
        )
    case_count = len(cases)
    return LLMJudgeAggregateMetrics(
        case_count=case_count,
        mean_correctness=_mean(case.correctness for case in cases),
        mean_completeness=_mean(case.completeness for case in cases),
        mean_groundedness=_mean(case.groundedness for case in cases),
        mean_citation_accuracy=_mean(case.citation_accuracy for case in cases),
        mean_refusal_quality=_mean(case.refusal_quality for case in cases),
        mean_usefulness=_mean(case.usefulness for case in cases),
        mean_overall_score=_mean(case.overall_score for case in cases),
    )


def _mean(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _score(value: object) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return round(max(0.0, min(1.0, float(value))), 4)
