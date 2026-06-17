from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class AnswerSource:
    source_id: str
    text: str
    relative_path: str | None = None


@dataclass(frozen=True)
class AnswerEvaluationCase:
    id: str
    question: str
    expected_terms: set[str] = field(default_factory=set)
    required_citations: bool = True
    should_refuse: bool = False
    insufficient_evidence_terms: set[str] = field(
        default_factory=lambda: {"insufficient", "not enough", "not provided"}
    )
    notes: str | None = None


@dataclass(frozen=True)
class AnswerCandidate:
    answer: str
    sources: list[AnswerSource]


@dataclass(frozen=True)
class AnswerCaseMetrics:
    case_id: str
    question: str
    expected_term_count: int
    covered_term_count: int
    cited_source_count: int
    invalid_citation_count: int
    correctness: float
    completeness: float
    groundedness: float
    citation_accuracy: float
    refusal_quality: float
    usefulness: float
    overall_score: float
    findings: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AnswerAggregateMetrics:
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
class AnswerEvaluationReport:
    generated_at: str
    metric_type: str
    aggregate: AnswerAggregateMetrics
    cases: list[AnswerCaseMetrics]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "metric_type": self.metric_type,
            "aggregate": self.aggregate.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }


class AnswerSourceLike(Protocol):
    source_id: str
    text: str
    relative_path: str


def evaluate_answer_cases(
    cases: list[AnswerEvaluationCase],
    candidates_by_case: dict[str, AnswerCandidate],
    *,
    generated_at: str | None = None,
) -> AnswerEvaluationReport:
    case_metrics = [
        evaluate_answer_case(
            case,
            candidates_by_case.get(case.id, AnswerCandidate(answer="", sources=[])),
        )
        for case in cases
    ]
    return AnswerEvaluationReport(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        metric_type="answer_quality",
        aggregate=_aggregate_answer_metrics(case_metrics),
        cases=case_metrics,
    )


def evaluate_answer_case(
    case: AnswerEvaluationCase,
    candidate: AnswerCandidate,
) -> AnswerCaseMetrics:
    answer = candidate.answer.strip()
    answer_text = answer.casefold()
    source_by_id = {source.source_id: source for source in candidate.sources}
    cited_ids = _citation_ids(answer)
    valid_cited_ids = [source_id for source_id in cited_ids if source_id in source_by_id]
    invalid_citation_count = len(cited_ids) - len(valid_cited_ids)
    covered_terms = {
        term for term in case.expected_terms if term.casefold() in answer_text
    }
    supported_terms = _supported_terms(
        expected_terms=case.expected_terms,
        cited_sources=[source_by_id[source_id] for source_id in valid_cited_ids],
    )

    if case.should_refuse:
        refusal_quality = _refusal_quality(answer_text, case.insufficient_evidence_terms)
        correctness = refusal_quality
        completeness = refusal_quality
        groundedness = 1.0 if not valid_cited_ids else 0.5
        citation_accuracy = 1.0 if invalid_citation_count == 0 else 0.0
        usefulness = refusal_quality
    else:
        expected_count = len(case.expected_terms)
        correctness = _ratio(len(covered_terms), expected_count)
        completeness = correctness
        groundedness = _ratio(len(supported_terms), max(1, len(covered_terms)))
        citation_accuracy = _citation_accuracy(
            required=case.required_citations,
            cited_count=len(cited_ids),
            invalid_count=invalid_citation_count,
        )
        refusal_quality = 1.0
        usefulness = (correctness + groundedness + citation_accuracy) / 3

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
    findings = _findings(
        case=case,
        covered_terms=covered_terms,
        supported_terms=supported_terms,
        cited_ids=cited_ids,
        invalid_citation_count=invalid_citation_count,
        refusal_quality=refusal_quality,
    )
    return AnswerCaseMetrics(
        case_id=case.id,
        question=case.question,
        expected_term_count=len(case.expected_terms),
        covered_term_count=len(covered_terms),
        cited_source_count=len(valid_cited_ids),
        invalid_citation_count=invalid_citation_count,
        correctness=_score(correctness),
        completeness=_score(completeness),
        groundedness=_score(groundedness),
        citation_accuracy=_score(citation_accuracy),
        refusal_quality=_score(refusal_quality),
        usefulness=_score(usefulness),
        overall_score=overall_score,
        findings=findings,
    )


def _aggregate_answer_metrics(cases: list[AnswerCaseMetrics]) -> AnswerAggregateMetrics:
    if not cases:
        return AnswerAggregateMetrics(
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
    return AnswerAggregateMetrics(
        case_count=case_count,
        mean_correctness=_score(sum(case.correctness for case in cases) / case_count),
        mean_completeness=_score(sum(case.completeness for case in cases) / case_count),
        mean_groundedness=_score(sum(case.groundedness for case in cases) / case_count),
        mean_citation_accuracy=_score(
            sum(case.citation_accuracy for case in cases) / case_count
        ),
        mean_refusal_quality=_score(
            sum(case.refusal_quality for case in cases) / case_count
        ),
        mean_usefulness=_score(sum(case.usefulness for case in cases) / case_count),
        mean_overall_score=_score(
            sum(case.overall_score for case in cases) / case_count
        ),
    )


def _citation_ids(answer: str) -> list[str]:
    return re.findall(r"\[(S\d+)\]", answer)


def _supported_terms(
    *,
    expected_terms: set[str],
    cited_sources: list[AnswerSource],
) -> set[str]:
    source_text = " ".join(source.text for source in cited_sources).casefold()
    return {term for term in expected_terms if term.casefold() in source_text}


def _citation_accuracy(*, required: bool, cited_count: int, invalid_count: int) -> float:
    if not required and cited_count == 0:
        return 1.0
    if required and cited_count == 0:
        return 0.0
    return _ratio(cited_count - invalid_count, cited_count)


def _refusal_quality(answer_text: str, insufficient_evidence_terms: set[str]) -> float:
    if any(term.casefold() in answer_text for term in insufficient_evidence_terms):
        return 1.0
    return 0.0


def _findings(
    *,
    case: AnswerEvaluationCase,
    covered_terms: set[str],
    supported_terms: set[str],
    cited_ids: list[str],
    invalid_citation_count: int,
    refusal_quality: float,
) -> list[str]:
    findings: list[str] = []
    missing_terms = sorted(case.expected_terms - covered_terms)
    unsupported_terms = sorted(covered_terms - supported_terms)
    if missing_terms:
        findings.append(f"Missing expected terms: {', '.join(missing_terms)}.")
    if unsupported_terms:
        findings.append(f"Covered terms lack cited support: {', '.join(unsupported_terms)}.")
    if case.required_citations and not case.should_refuse and not cited_ids:
        findings.append("Answer did not cite any sources.")
    if invalid_citation_count:
        findings.append(f"Answer used {invalid_citation_count} invalid citation(s).")
    if case.should_refuse and refusal_quality < 1:
        findings.append("Answer should have said the evidence was insufficient.")
    if not findings:
        findings.append("Case passed the deterministic answer-quality checks.")
    return findings


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return numerator / denominator


def _score(value: float) -> float:
    return round(value, 4)
