from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from librarian_evaluation.retrieval import (
    RetrievalCaseMetrics,
    RetrievalEvaluationReport,
)


@dataclass(frozen=True)
class RetrievalReportDocument:
    report_type: str
    benchmark: dict[str, Any]
    summary: dict[str, Any]
    retrieval: RetrievalEvaluationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "benchmark": self.benchmark,
            "summary": self.summary,
            "retrieval": self.retrieval.to_dict(),
        }


def build_retrieval_report_document(
    report: RetrievalEvaluationReport,
    *,
    benchmark: dict[str, Any] | None = None,
    primary_k: int | None = None,
) -> RetrievalReportDocument:
    selected_k = primary_k or max(report.k_values)
    if selected_k not in report.k_values:
        raise ValueError(f"primary_k must be one of {report.k_values}")

    summary = _summarize_retrieval_report(report, selected_k)
    return RetrievalReportDocument(
        report_type="retrieval_evaluation",
        benchmark=benchmark or {},
        summary=summary,
        retrieval=report,
    )


def _summarize_retrieval_report(
    report: RetrievalEvaluationReport,
    primary_k: int,
) -> dict[str, Any]:
    aggregate = report.aggregate
    hit_rate = aggregate.hit_rate_at_k[primary_k]
    precision = aggregate.mean_precision_at_k[primary_k]
    recall = aggregate.mean_recall_at_k[primary_k]
    mrr = aggregate.mean_reciprocal_rank
    overall_score = round((hit_rate + recall + mrr) / 3, 4)

    return {
        "primary_k": primary_k,
        "overall_score": overall_score,
        "headline": _headline(
            case_count=aggregate.case_count,
            hit_rate=hit_rate,
            recall=recall,
            mrr=mrr,
            primary_k=primary_k,
        ),
        "key_metrics": {
            "hit_rate_at_k": hit_rate,
            "mean_precision_at_k": precision,
            "mean_recall_at_k": recall,
            "mean_reciprocal_rank": mrr,
        },
        "improvement_areas": _improvement_areas(
            hit_rate=hit_rate,
            precision=precision,
            recall=recall,
            mrr=mrr,
            primary_k=primary_k,
        ),
        "weakest_cases": [_case_finding(case, primary_k) for case in _weakest_cases(report, primary_k)],
    }


def _headline(
    *,
    case_count: int,
    hit_rate: float,
    recall: float,
    mrr: float,
    primary_k: int,
) -> str:
    return (
        f"{case_count} retrieval cases evaluated. "
        f"Hit@{primary_k} is {_percent(hit_rate)}, "
        f"Recall@{primary_k} is {_percent(recall)}, "
        f"and MRR is {_percent(mrr)}."
    )


def _improvement_areas(
    *,
    hit_rate: float,
    precision: float,
    recall: float,
    mrr: float,
    primary_k: int,
) -> list[str]:
    areas: list[str] = []
    if hit_rate < 0.8:
        areas.append(
            f"Candidate generation: some benchmark queries do not retrieve relevant evidence in the top {primary_k}."
        )
    if recall < 0.8:
        areas.append(
            f"Coverage: relevant evidence is missing from the top {primary_k}; improve chunking, metadata filters, or hybrid retrieval."
        )
    if precision < 0.5:
        areas.append(
            f"Noise: fewer than half of the top {primary_k} results are relevant on average; improve filtering or reranking."
        )
    if mrr < 0.8:
        areas.append(
            "Ranking: relevant evidence is not consistently near rank 1; reranking is likely the next useful lever."
        )
    if not areas:
        areas.append("No urgent retrieval weakness detected by the current benchmark.")
    return areas


def _weakest_cases(
    report: RetrievalEvaluationReport,
    primary_k: int,
) -> list[RetrievalCaseMetrics]:
    weak_cases = [
        case
        for case in report.cases
        if not case.hit_at_k[primary_k]
        or case.recall_at_k[primary_k] < 1
        or case.reciprocal_rank < 1
    ]
    cases_to_rank = weak_cases or report.cases
    return sorted(
        cases_to_rank,
        key=lambda case: (
            case.recall_at_k[primary_k],
            case.reciprocal_rank,
            case.precision_at_k[primary_k],
        ),
    )[:5]


def _case_finding(case: RetrievalCaseMetrics, primary_k: int) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "query": case.query,
        "hit_at_k": case.hit_at_k[primary_k],
        "precision_at_k": case.precision_at_k[primary_k],
        "recall_at_k": case.recall_at_k[primary_k],
        "reciprocal_rank": case.reciprocal_rank,
        "reason": _case_reason(case, primary_k),
    }


def _case_reason(case: RetrievalCaseMetrics, primary_k: int) -> str:
    if not case.hit_at_k[primary_k]:
        return f"No relevant evidence appeared in the top {primary_k}."
    if case.recall_at_k[primary_k] < 1:
        return f"Some relevant evidence appeared, but Recall@{primary_k} is incomplete."
    if case.reciprocal_rank < 1:
        return "Relevant evidence appeared, but not at rank 1."
    return "Case passed the current retrieval target."


def _percent(value: float) -> str:
    return f"{value:.0%}"
