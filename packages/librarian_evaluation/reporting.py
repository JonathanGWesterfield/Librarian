from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from librarian_evaluation.answer import AnswerEvaluationReport
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
    run: dict[str, Any] | None = None
    answer_quality: AnswerEvaluationReport | None = None

    def to_dict(self) -> dict[str, Any]:
        document = {
            "report_type": self.report_type,
            "benchmark": self.benchmark,
            "summary": self.summary,
            "retrieval": self.retrieval.to_dict(),
        }
        if self.run is not None:
            document["run"] = self.run
        if self.answer_quality is not None:
            document["answer_quality"] = self.answer_quality.to_dict()
        return document


def build_retrieval_report_document(
    report: RetrievalEvaluationReport,
    *,
    benchmark: dict[str, Any] | None = None,
    primary_k: int | None = None,
    run: dict[str, Any] | None = None,
    answer_quality: AnswerEvaluationReport | None = None,
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
        run=run,
        answer_quality=answer_quality,
    )


def render_evaluation_markdown(
    document: dict[str, Any],
    *,
    golden_corpus: dict[str, Any] | None = None,
) -> str:
    retrieval = document["retrieval"]
    summary = document["summary"]
    benchmark = document.get("benchmark", {})
    run = document.get("run", {})
    answer_quality = document.get("answer_quality")
    golden_corpus = golden_corpus or {}
    lines = [
        "# Librarian Evaluation Report",
        "",
        "## Overview",
        "",
        summary["headline"],
        "",
        f"- Overall retrieval score: `{summary['overall_score']}`",
        f"- Primary K: `{summary['primary_k']}`",
        f"- Active benchmark: `{benchmark.get('name', 'unknown')}`",
        f"- Benchmark mode: `{benchmark.get('mode', 'unknown')}`",
        "",
    ]
    lines.extend(_render_run_metadata_section(run))
    lines.extend(_render_embedding_section(run, benchmark))
    lines.extend(["", "## Golden Corpus", ""])
    lines.extend(_render_golden_corpus_section(golden_corpus, benchmark))
    lines.extend(
        [
            "",
            "## Retrieval Metrics",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Case count | `{retrieval['aggregate']['case_count']}` |",
            f"| Hit@{summary['primary_k']} | `{_decimal(summary['key_metrics']['hit_rate_at_k'])}` |",
            f"| Precision@{summary['primary_k']} | `{_decimal(summary['key_metrics']['mean_precision_at_k'])}` |",
            f"| Recall@{summary['primary_k']} | `{_decimal(summary['key_metrics']['mean_recall_at_k'])}` |",
            f"| Mean reciprocal rank | `{_decimal(summary['key_metrics']['mean_reciprocal_rank'])}` |",
            "",
            "### Improvement Areas",
            "",
        ]
    )
    lines.extend([f"- {area}" for area in summary["improvement_areas"]])
    lines.extend(["", "## Answer Quality", ""])
    lines.extend(_render_answer_quality_section(answer_quality, run))
    lines.extend(["", "### Weakest Cases", ""])
    lines.extend(_render_weakest_cases(summary["weakest_cases"], summary["primary_k"]))
    lines.extend(["", "### Retrieval Cases", ""])
    lines.extend(_render_case_table(retrieval["cases"], summary["primary_k"]))
    lines.extend(
        [
            "",
            "## Report Freshness",
            "",
            "GitHub Actions runs `scripts/check.sh`, which validates that the",
            "committed JSON and Markdown reports match the current evaluation",
            "fixture data.",
            "",
        ]
    )
    return "\n".join(lines)


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


def _render_embedding_section(
    run: dict[str, Any],
    benchmark: dict[str, Any],
) -> list[str]:
    if run.get("mode") == "live_search":
        return [
            "## Embeddings",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            "| Live embedding evaluation | Measured through live retrieval |",
            f"| Embedding provider | `{run.get('embedding_provider', 'unknown')}` |",
            f"| Embedding model | `{run.get('embedding_model', 'unknown')}` |",
            f"| Embedding dimensions | `{run.get('embedding_dimensions', 'unknown')}` |",
            f"| Search limit per query | `{run.get('limit', 'unknown')}` |",
            f"| Total candidates scored | `{run.get('total_candidates_scored', 'unknown')}` |",
            f"| Search total latency | `{_seconds(run.get('search_total_seconds', 'unknown'))}` |",
            f"| Search mean latency | `{_seconds(run.get('search_mean_seconds', 'unknown'))}` |",
            f"| Search max latency | `{_seconds(run.get('search_max_seconds', 'unknown'))}` |",
            "",
            "This section does not judge embedding quality directly. It measures",
            "embedding impact through retrieval outcomes against the golden corpus.",
        ]
    return [
        "## Embeddings",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        "| Live embedding evaluation | Not measured in this smoke report |",
        "| Embedding provider | Not available until live retrieval is run |",
        "| Embedding model | Not available until live retrieval is run |",
        f"| Benchmark mode | `{benchmark.get('mode', 'unknown')}` |",
        "| What this section should answer | Whether embedding model changes improve retrieval quality |",
        "",
        "This smoke report does not call the local database. Run",
        "`python3 scripts/evaluate_retrieval.py --live` to populate this",
        "section with live embedding and search metadata.",
    ]


def _render_golden_corpus_section(
    golden_corpus: dict[str, Any],
    active_benchmark: dict[str, Any],
) -> list[str]:
    if not golden_corpus:
        return [
            "Golden corpus metadata was not provided to this report run.",
        ]
    benchmark = golden_corpus.get("benchmark", {})
    cases = golden_corpus.get("cases", [])
    expected_book_count = sum(
        len(case.get("relevant_relative_paths", [])) for case in cases
    )
    lines = [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Corpus name | `{benchmark.get('name', 'unknown')}` |",
        f"| Corpus mode | `{benchmark.get('mode', 'unknown')}` |",
        f"| Label granularity | `{golden_corpus.get('label_granularity', 'unknown')}` |",
        f"| Query cases | `{len(cases)}` |",
        f"| Expected book labels | `{expected_book_count}` |",
        f"| Primary K | `{golden_corpus.get('primary_k', 'unknown')}` |",
        f"| Used by active report | `{active_benchmark.get('name') == benchmark.get('name')}` |",
        "",
        "The golden corpus is the real-library benchmark. It is currently",
        "book-level. In live mode, each query is run through search and scored",
        "against these expected EPUB filenames.",
        "",
        "### Golden Corpus Cases",
        "",
        "| Case | Expected Books |",
        "| --- | ---: |",
    ]
    for case in cases:
        lines.append(
            f"| `{case['id']}` | `{len(case.get('relevant_relative_paths', []))}` |"
        )
    return lines


def _render_answer_quality_section(
    answer_quality: dict[str, Any] | None,
    run: dict[str, Any],
) -> list[str]:
    if not answer_quality:
        return [
            "Answer quality was not measured for this report.",
            "",
            "This section should track correctness, completeness, groundedness,",
            "citation accuracy, usefulness, and refusal behavior.",
        ]

    aggregate = answer_quality["aggregate"]
    lines: list[str] = []
    answer_run = run.get("answer_quality", {})
    if answer_run.get("mode") == "live_chat":
        lines.extend(
            [
                "### Answer Generation",
                "",
                "| Metric | Value |",
                "| --- | --- |",
                "| Live answer evaluation | Measured through live chat |",
                f"| Generation provider | `{answer_run.get('generation_provider', 'unknown')}` |",
                f"| Generation model | `{answer_run.get('generation_model', 'unknown')}` |",
                f"| Embedding provider | `{answer_run.get('embedding_provider', 'unknown')}` |",
                f"| Embedding model | `{answer_run.get('embedding_model', 'unknown')}` |",
                f"| Retrieval limit | `{answer_run.get('retrieval_limit', 'unknown')}` |",
                f"| Questions evaluated | `{answer_run.get('question_count', 'unknown')}` |",
                f"| Sources returned | `{answer_run.get('total_sources_returned', 'unknown')}` |",
                f"| Answer total latency | `{_seconds(answer_run.get('answer_total_seconds', 'unknown'))}` |",
                f"| Answer mean latency | `{_seconds(answer_run.get('answer_mean_seconds', 'unknown'))}` |",
                f"| Answer max latency | `{_seconds(answer_run.get('answer_max_seconds', 'unknown'))}` |",
                "",
                "### Answer Metrics",
                "",
            ]
        )

    lines.extend(
        [
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Case count | `{aggregate['case_count']}` |",
        f"| Correctness | `{_decimal(aggregate['mean_correctness'])}` |",
        f"| Completeness | `{_decimal(aggregate['mean_completeness'])}` |",
        f"| Groundedness | `{_decimal(aggregate['mean_groundedness'])}` |",
        f"| Citation accuracy | `{_decimal(aggregate['mean_citation_accuracy'])}` |",
        f"| Refusal quality | `{_decimal(aggregate['mean_refusal_quality'])}` |",
        f"| Usefulness | `{_decimal(aggregate['mean_usefulness'])}` |",
        f"| Overall answer score | `{_decimal(aggregate['mean_overall_score'])}` |",
        "",
        "### Answer Quality Cases",
        "",
        "| Case | Overall | Correctness | Groundedness | Citation Accuracy | Findings |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for case in answer_quality["cases"]:
        findings = "<br>".join(case["findings"])
        lines.append(
            "| "
            f"`{case['case_id']}` | "
            f"`{_decimal(case['overall_score'])}` | "
            f"`{_decimal(case['correctness'])}` | "
            f"`{_decimal(case['groundedness'])}` | "
            f"`{_decimal(case['citation_accuracy'])}` | "
            f"{findings} |"
        )
    return lines


def _render_run_metadata_section(run: dict[str, Any]) -> list[str]:
    execution = run.get("execution")
    git = run.get("git")
    if not execution and not git:
        return []

    lines = ["## Run Metadata", "", "| Metric | Value |", "| --- | --- |"]
    if execution:
        lines.extend(
            [
                f"| Started at | `{execution.get('started_at', 'unknown')}` |",
                f"| Elapsed time | `{_seconds(execution.get('elapsed_seconds', 'unknown'))}` |",
            ]
        )
    if git:
        lines.extend(
            [
                f"| Git commit | `{git.get('short_commit', 'unknown')}` |",
                f"| Git branch | `{git.get('branch', 'unknown')}` |",
                f"| Git dirty | `{git.get('dirty', 'unknown')}` |",
            ]
        )
    lines.append("")
    return lines


def _render_weakest_cases(cases: list[dict[str, Any]], primary_k: int) -> list[str]:
    if not cases:
        return ["No weak cases detected."]
    lines = [
        f"| Case | Hit@{primary_k} | Recall@{primary_k} | MRR | Reason |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for case in cases:
        lines.append(
            "| "
            f"`{case['case_id']}` | "
            f"`{case['hit_at_k']}` | "
            f"`{_decimal(case['recall_at_k'])}` | "
            f"`{_decimal(case['reciprocal_rank'])}` | "
            f"{case['reason']} |"
        )
    return lines


def _render_case_table(cases: list[dict[str, Any]], primary_k: int) -> list[str]:
    lines = [
        f"| Case | Results | Relevant Results | Hit@{primary_k} | Precision@{primary_k} | Recall@{primary_k} | MRR |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in cases:
        lines.append(
            "| "
            f"`{case['case_id']}` | "
            f"`{case['result_count']}` | "
            f"`{case['relevant_result_count']}` | "
            f"`{_metric_at_k(case['hit_at_k'], primary_k)}` | "
            f"`{_decimal(_metric_at_k(case['precision_at_k'], primary_k))}` | "
            f"`{_decimal(_metric_at_k(case['recall_at_k'], primary_k))}` | "
            f"`{_decimal(case['reciprocal_rank'])}` |"
        )
    return lines


def _decimal(value: float) -> str:
    return f"{value:.4f}"


def _seconds(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.4f}s"
    return str(value)


def _metric_at_k(metrics: dict[Any, Any], k: int) -> Any:
    if k in metrics:
        return metrics[k]
    return metrics[str(k)]
