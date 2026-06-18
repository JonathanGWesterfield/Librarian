from __future__ import annotations

from typing import Any


HIGHER_IS_BETTER = "higher_is_better"
LOWER_IS_BETTER = "lower_is_better"


def compare_report_documents(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    baseline_label: str = "baseline",
) -> dict[str, Any]:
    metrics = []
    metrics.extend(_retrieval_metrics(current, baseline))
    metrics.extend(_answer_metrics(current, baseline))
    metrics.extend(_latency_metrics(current, baseline))
    return {
        "baseline": baseline_label,
        "current": _report_identity(current),
        "metric_count": len(metrics),
        "improved_count": sum(
            1 for metric in metrics if metric["status"] == "improved"
        ),
        "regressed_count": sum(
            1 for metric in metrics if metric["status"] == "regressed"
        ),
        "unchanged_count": sum(
            1 for metric in metrics if metric["status"] == "unchanged"
        ),
        "metrics": metrics,
    }


def _retrieval_metrics(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    current_summary = current.get("summary", {})
    baseline_summary = baseline.get("summary", {})
    current_key_metrics = current_summary.get("key_metrics", {})
    baseline_key_metrics = baseline_summary.get("key_metrics", {})
    primary_k = current_summary.get("primary_k", "K")
    return _metric_rows(
        [
            (
                "retrieval",
                "overall_score",
                current_summary.get("overall_score"),
                baseline_summary.get("overall_score"),
                HIGHER_IS_BETTER,
            ),
            (
                "retrieval",
                f"hit_at_{primary_k}",
                current_key_metrics.get("hit_rate_at_k"),
                baseline_key_metrics.get("hit_rate_at_k"),
                HIGHER_IS_BETTER,
            ),
            (
                "retrieval",
                f"precision_at_{primary_k}",
                current_key_metrics.get("mean_precision_at_k"),
                baseline_key_metrics.get("mean_precision_at_k"),
                HIGHER_IS_BETTER,
            ),
            (
                "retrieval",
                f"recall_at_{primary_k}",
                current_key_metrics.get("mean_recall_at_k"),
                baseline_key_metrics.get("mean_recall_at_k"),
                HIGHER_IS_BETTER,
            ),
            (
                "retrieval",
                "mean_reciprocal_rank",
                current_key_metrics.get("mean_reciprocal_rank"),
                baseline_key_metrics.get("mean_reciprocal_rank"),
                HIGHER_IS_BETTER,
            ),
        ]
    )


def _answer_metrics(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    current_aggregate = current.get("answer_quality", {}).get("aggregate", {})
    baseline_aggregate = baseline.get("answer_quality", {}).get("aggregate", {})
    return _metric_rows(
        [
            (
                "answer_quality",
                "overall_score",
                current_aggregate.get("mean_overall_score"),
                baseline_aggregate.get("mean_overall_score"),
                HIGHER_IS_BETTER,
            ),
            (
                "answer_quality",
                "correctness",
                current_aggregate.get("mean_correctness"),
                baseline_aggregate.get("mean_correctness"),
                HIGHER_IS_BETTER,
            ),
            (
                "answer_quality",
                "groundedness",
                current_aggregate.get("mean_groundedness"),
                baseline_aggregate.get("mean_groundedness"),
                HIGHER_IS_BETTER,
            ),
            (
                "answer_quality",
                "citation_accuracy",
                current_aggregate.get("mean_citation_accuracy"),
                baseline_aggregate.get("mean_citation_accuracy"),
                HIGHER_IS_BETTER,
            ),
            (
                "answer_quality",
                "refusal_quality",
                current_aggregate.get("mean_refusal_quality"),
                baseline_aggregate.get("mean_refusal_quality"),
                HIGHER_IS_BETTER,
            ),
            (
                "answer_quality",
                "usefulness",
                current_aggregate.get("mean_usefulness"),
                baseline_aggregate.get("mean_usefulness"),
                HIGHER_IS_BETTER,
            ),
        ]
    )


def _latency_metrics(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    current_run = current.get("run", {})
    baseline_run = baseline.get("run", {})
    current_answer = current_run.get("answer_quality", {})
    baseline_answer = baseline_run.get("answer_quality", {})
    return _metric_rows(
        [
            (
                "latency",
                "elapsed_seconds",
                current_run.get("execution", {}).get("elapsed_seconds"),
                baseline_run.get("execution", {}).get("elapsed_seconds"),
                LOWER_IS_BETTER,
            ),
            (
                "latency",
                "search_total_seconds",
                current_run.get("search_total_seconds"),
                baseline_run.get("search_total_seconds"),
                LOWER_IS_BETTER,
            ),
            (
                "latency",
                "answer_total_seconds",
                current_answer.get("answer_total_seconds"),
                baseline_answer.get("answer_total_seconds"),
                LOWER_IS_BETTER,
            ),
        ]
    )


def _metric_rows(
    rows: list[tuple[str, str, Any, Any, str]],
) -> list[dict[str, Any]]:
    metrics = []
    for section, name, current, baseline, direction in rows:
        if not _is_number(current) or not _is_number(baseline):
            continue
        delta = round(float(current) - float(baseline), 4)
        metrics.append(
            {
                "section": section,
                "name": name,
                "current": _round_metric(current),
                "baseline": _round_metric(baseline),
                "delta": delta,
                "direction": direction,
                "status": _metric_status(delta, direction),
            }
        )
    return metrics


def _metric_status(delta: float, direction: str) -> str:
    if delta == 0:
        return "unchanged"
    if direction == LOWER_IS_BETTER:
        return "improved" if delta < 0 else "regressed"
    return "improved" if delta > 0 else "regressed"


def _report_identity(document: dict[str, Any]) -> dict[str, Any]:
    run = document.get("run", {})
    git = run.get("git", {})
    return {
        "benchmark": document.get("benchmark", {}).get("name", "unknown"),
        "commit": git.get("short_commit", "unknown"),
        "branch": git.get("branch", "unknown"),
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _round_metric(value: Any) -> float:
    return round(float(value), 4)
