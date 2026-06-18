from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Protocol
from urllib import error, request

from librarian_evaluation.answer import AnswerCandidate, AnswerEvaluationCase


class LLMJudgeError(RuntimeError):
    pass


class LLMJudge(Protocol):
    provider: str
    model: str

    def judge(self, prompt: str) -> str:
        ...


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
    rationale: str

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
                ["codex", "exec", "--ephemeral", prompt],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LLMJudgeError(f"could not run Codex judge: {exc}") from exc
        return completed.stdout.strip()


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
    sources = "\n\n".join(
        f"[{source.source_id}] {source.relative_path or 'unknown source'}\n{source.text}"
        for source in candidate.sources
    )
    expected_terms = ", ".join(sorted(case.expected_terms)) or "none"
    return (
        "Evaluate the answer for a retrieval-augmented book assistant.\n"
        "Return only valid JSON with numeric scores from 0.0 to 1.0 and a short rationale.\n"
        "Use these keys exactly: correctness, completeness, groundedness, "
        "citation_accuracy, refusal_quality, usefulness, overall_score, rationale.\n\n"
        f"Question:\n{case.question}\n\n"
        f"Expected concepts:\n{expected_terms}\n\n"
        f"Should refuse for insufficient evidence:\n{case.should_refuse}\n\n"
        f"Answer:\n{candidate.answer}\n\n"
        f"Sources:\n{sources or 'No sources provided.'}"
    )


def _case_metrics_from_response(
    case: AnswerEvaluationCase,
    response: str,
    *,
    provider: str,
    model: str,
) -> LLMJudgeCaseMetrics:
    payload = _extract_json_object(response)
    return LLMJudgeCaseMetrics(
        case_id=case.id,
        question=case.question,
        provider=provider,
        model=model,
        correctness=_score(payload.get("correctness")),
        completeness=_score(payload.get("completeness")),
        groundedness=_score(payload.get("groundedness")),
        citation_accuracy=_score(payload.get("citation_accuracy")),
        refusal_quality=_score(payload.get("refusal_quality")),
        usefulness=_score(payload.get("usefulness")),
        overall_score=_score(payload.get("overall_score")),
        rationale=str(payload.get("rationale", "")).strip(),
    )


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
