from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    book_id: str
    relative_path: str
    score: float | None = None
    title: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    id: str
    query: str
    relevant_chunk_ids: set[str] = field(default_factory=set)
    relevant_book_ids: set[str] = field(default_factory=set)
    relevant_relative_paths: set[str] = field(default_factory=set)
    notes: str | None = None


@dataclass(frozen=True)
class RetrievalCaseMetrics:
    case_id: str
    query: str
    result_count: int
    relevant_result_count: int
    expected_relevant_count: int
    hit_at_k: dict[int, bool]
    precision_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    reciprocal_rank: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalAggregateMetrics:
    case_count: int
    hit_rate_at_k: dict[int, float]
    mean_precision_at_k: dict[int, float]
    mean_recall_at_k: dict[int, float]
    mean_reciprocal_rank: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    generated_at: str
    metric_type: str
    k_values: list[int]
    aggregate: RetrievalAggregateMetrics
    cases: list[RetrievalCaseMetrics]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "metric_type": self.metric_type,
            "k_values": self.k_values,
            "aggregate": self.aggregate.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }


class RetrievalResultLike(Protocol):
    chunk_id: str
    book_id: str
    relative_path: str
    score: float
    title: str | None
    text: str


def evaluate_retrieval_cases(
    cases: list[RetrievalEvaluationCase],
    ranked_results_by_case: dict[str, list[RetrievalResult | RetrievalResultLike]],
    *,
    k_values: list[int] | None = None,
) -> RetrievalEvaluationReport:
    normalized_k_values = sorted(set(k_values or [1, 3, 5, 10]))
    case_metrics = [
        evaluate_retrieval_case(
            case,
            ranked_results_by_case.get(case.id, []),
            k_values=normalized_k_values,
        )
        for case in cases
    ]
    return RetrievalEvaluationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        metric_type="retrieval",
        k_values=normalized_k_values,
        aggregate=_aggregate_case_metrics(case_metrics, normalized_k_values),
        cases=case_metrics,
    )


def evaluate_retrieval_case(
    case: RetrievalEvaluationCase,
    ranked_results: list[RetrievalResult | RetrievalResultLike],
    *,
    k_values: list[int] | None = None,
) -> RetrievalCaseMetrics:
    normalized_k_values = sorted(set(k_values or [1, 3, 5, 10]))
    relevance = [_is_relevant(case, result) for result in ranked_results]
    expected_relevant_count = _expected_relevant_count(case)
    relevant_result_count = sum(1 for is_relevant in relevance if is_relevant)
    hit_at_k: dict[int, bool] = {}
    precision_at_k: dict[int, float] = {}
    recall_at_k: dict[int, float] = {}

    for k in normalized_k_values:
        top_k = relevance[:k]
        top_k_relevant_count = sum(1 for is_relevant in top_k if is_relevant)
        hit_at_k[k] = top_k_relevant_count > 0
        precision_at_k[k] = top_k_relevant_count / k
        recall_at_k[k] = (
            top_k_relevant_count / expected_relevant_count
            if expected_relevant_count > 0
            else 0.0
        )

    return RetrievalCaseMetrics(
        case_id=case.id,
        query=case.query,
        result_count=len(ranked_results),
        relevant_result_count=relevant_result_count,
        expected_relevant_count=expected_relevant_count,
        hit_at_k=hit_at_k,
        precision_at_k=precision_at_k,
        recall_at_k=recall_at_k,
        reciprocal_rank=_reciprocal_rank(relevance),
    )


def _aggregate_case_metrics(
    cases: list[RetrievalCaseMetrics],
    k_values: list[int],
) -> RetrievalAggregateMetrics:
    if not cases:
        return RetrievalAggregateMetrics(
            case_count=0,
            hit_rate_at_k={k: 0.0 for k in k_values},
            mean_precision_at_k={k: 0.0 for k in k_values},
            mean_recall_at_k={k: 0.0 for k in k_values},
            mean_reciprocal_rank=0.0,
        )

    case_count = len(cases)
    return RetrievalAggregateMetrics(
        case_count=case_count,
        hit_rate_at_k={
            k: sum(1 for case in cases if case.hit_at_k[k]) / case_count
            for k in k_values
        },
        mean_precision_at_k={
            k: sum(case.precision_at_k[k] for case in cases) / case_count
            for k in k_values
        },
        mean_recall_at_k={
            k: sum(case.recall_at_k[k] for case in cases) / case_count
            for k in k_values
        },
        mean_reciprocal_rank=(
            sum(case.reciprocal_rank for case in cases) / case_count
        ),
    )


def _is_relevant(
    case: RetrievalEvaluationCase,
    result: RetrievalResult | RetrievalResultLike,
) -> bool:
    return (
        result.chunk_id in case.relevant_chunk_ids
        or result.book_id in case.relevant_book_ids
        or result.relative_path in case.relevant_relative_paths
    )


def _expected_relevant_count(case: RetrievalEvaluationCase) -> int:
    return max(
        len(case.relevant_chunk_ids),
        len(case.relevant_book_ids),
        len(case.relevant_relative_paths),
    )


def _reciprocal_rank(relevance: list[bool]) -> float:
    for index, is_relevant in enumerate(relevance, start=1):
        if is_relevant:
            return 1 / index
    return 0.0
