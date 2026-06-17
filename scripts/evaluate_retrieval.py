#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_evaluation.reporting import (
    build_retrieval_report_document,
    render_evaluation_markdown,
)
from librarian_evaluation.answer import (
    AnswerCandidate,
    AnswerEvaluationCase,
    AnswerSource,
    evaluate_answer_cases,
)
from librarian_evaluation.retrieval import (
    RetrievalEvaluationCase,
    RetrievalResult,
    evaluate_retrieval_cases,
)
from librarian_search.search import SearchOptions, SearchResponse, search_chunks

DEFAULT_BENCHMARK_PATH = REPO_ROOT / "tests/fixtures/evaluation/retrieval_benchmark.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs/evaluation-retrieval-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = REPO_ROOT / "docs/evaluation-report.md"
DEFAULT_LIVE_OUTPUT_PATH = REPO_ROOT / "docs/evaluation-live-retrieval-report.json"
DEFAULT_LIVE_MARKDOWN_OUTPUT_PATH = REPO_ROOT / "docs/evaluation-live-report.md"
DEFAULT_GOLDEN_CORPUS_PATH = (
    REPO_ROOT / "tests/fixtures/evaluation/golden_retrieval_corpus.json"
)
DEFAULT_ANSWER_BENCHMARK_PATH = (
    REPO_ROOT / "tests/fixtures/evaluation/answer_quality_benchmark.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Librarian retrieval evaluation reports."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run the golden corpus through live search against the local database.",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=DEFAULT_BENCHMARK_PATH,
        help="Path to the retrieval benchmark JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the generated JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT_PATH,
        help="Path to write the generated human-readable Markdown report.",
    )
    parser.add_argument(
        "--golden-corpus",
        type=Path,
        default=DEFAULT_GOLDEN_CORPUS_PATH,
        help="Path to the real-library golden corpus JSON file.",
    )
    parser.add_argument(
        "--answer-benchmark",
        type=Path,
        default=DEFAULT_ANSWER_BENCHMARK_PATH,
        help="Path to the deterministic answer-quality benchmark JSON file.",
    )
    parser.add_argument(
        "--github-summary",
        type=Path,
        default=None,
        help="Optional path, usually GITHUB_STEP_SUMMARY, to append Markdown output.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL for live retrieval. Defaults to Librarian config.",
    )
    parser.add_argument(
        "--embedding-provider",
        default=None,
        help="Embedding provider for live query embeddings.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding model for live query embeddings.",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=None,
        help="Ollama base URL for live query embeddings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum live search results to score per golden corpus query.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output file does not match the generated report.",
    )
    args = parser.parse_args()

    if args.live:
        if args.output == DEFAULT_OUTPUT_PATH:
            args.output = DEFAULT_LIVE_OUTPUT_PATH
        if args.markdown_output == DEFAULT_MARKDOWN_OUTPUT_PATH:
            args.markdown_output = DEFAULT_LIVE_MARKDOWN_OUTPUT_PATH
        document = generate_live_report_document(
            args.golden_corpus,
            answer_benchmark_path=args.answer_benchmark,
            database_url=args.database_url,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            ollama_base_url=args.ollama_base_url,
            limit=args.limit,
        )
    else:
        document = generate_report_document(
            args.benchmark,
            answer_benchmark_path=args.answer_benchmark,
        )
    golden_corpus = _load_optional_json(args.golden_corpus)
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    rendered_markdown = render_evaluation_markdown(
        document,
        golden_corpus=golden_corpus,
    )

    if args.check:
        if _report_is_stale(
            args.output,
            rendered,
            regenerate_hint=f"run scripts/evaluate_retrieval.py --output {args.output}",
        ):
            return 1
        if _report_is_stale(
            args.markdown_output,
            rendered_markdown,
            regenerate_hint=(
                "run scripts/evaluate_retrieval.py "
                f"--markdown-output {args.markdown_output}"
            ),
        ):
            return 1
        if args.github_summary:
            _append_summary(args.github_summary, rendered_markdown)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(rendered_markdown, encoding="utf-8")
    if args.github_summary:
        _append_summary(args.github_summary, rendered_markdown)
    print(f"Wrote retrieval evaluation report to {args.output}")
    print(f"Wrote human-readable evaluation report to {args.markdown_output}")
    return 0


def generate_report_document(
    benchmark_path: Path,
    *,
    answer_benchmark_path: Path | None = None,
) -> dict[str, Any]:
    benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
    cases = [_case_from_json(case) for case in benchmark_data["cases"]]
    ranked_results_by_case = {
        case["id"]: [_result_from_json(result) for result in case.get("results", [])]
        for case in benchmark_data["cases"]
    }
    benchmark = benchmark_data.get("benchmark", {})
    report = evaluate_retrieval_cases(
        cases,
        ranked_results_by_case,
        k_values=benchmark_data.get("k_values"),
        generated_at=benchmark.get("generated_at"),
    )
    document = build_retrieval_report_document(
        report,
        benchmark=benchmark,
        primary_k=benchmark_data.get("primary_k"),
        answer_quality=_answer_report_from_path(answer_benchmark_path),
    )
    return document.to_dict()


def generate_live_report_document(
    corpus_path: Path,
    *,
    answer_benchmark_path: Path | None = None,
    database_url: str | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    ollama_base_url: str | None = None,
    limit: int = 10,
    search_fn=search_chunks,
) -> dict[str, Any]:
    corpus_data = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = [_case_from_json(case) for case in corpus_data["cases"]]
    ranked_results_by_case: dict[str, list] = {}
    responses: list[SearchResponse] = []

    for case in cases:
        response = search_fn(
            SearchOptions(
                query=case.query,
                database_url=database_url,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                ollama_base_url=ollama_base_url,
                limit=limit,
            )
        )
        responses.append(response)
        ranked_results_by_case[case.id] = response.results

    benchmark = dict(corpus_data.get("benchmark", {}))
    benchmark["mode"] = "live_search"
    report = evaluate_retrieval_cases(
        cases,
        ranked_results_by_case,
        k_values=corpus_data.get("k_values"),
    )
    document = build_retrieval_report_document(
        report,
        benchmark=benchmark,
        primary_k=corpus_data.get("primary_k"),
        run=_live_run_metadata(
            responses,
            database_url=database_url,
            limit=limit,
        ),
        answer_quality=_answer_report_from_path(answer_benchmark_path),
    )
    return document.to_dict()


def _case_from_json(data: dict[str, Any]) -> RetrievalEvaluationCase:
    return RetrievalEvaluationCase(
        id=data["id"],
        query=data["query"],
        relevant_chunk_ids=set(data.get("relevant_chunk_ids", [])),
        relevant_book_ids=set(data.get("relevant_book_ids", [])),
        relevant_relative_paths=set(data.get("relevant_relative_paths", [])),
        notes=data.get("notes"),
    )


def _result_from_json(data: dict[str, Any]) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=data["chunk_id"],
        book_id=data["book_id"],
        relative_path=data["relative_path"],
        score=data.get("score"),
        title=data.get("title"),
        text=data.get("text"),
    )


def _answer_report_from_path(path: Path | None):
    if path is None or not path.exists():
        return None
    benchmark_data = json.loads(path.read_text(encoding="utf-8"))
    cases = [_answer_case_from_json(case) for case in benchmark_data["cases"]]
    candidates = {
        case["id"]: _answer_candidate_from_json(case)
        for case in benchmark_data["cases"]
    }
    generated_at = benchmark_data.get("benchmark", {}).get("generated_at")
    return evaluate_answer_cases(cases, candidates, generated_at=generated_at)


def _answer_case_from_json(data: dict[str, Any]) -> AnswerEvaluationCase:
    return AnswerEvaluationCase(
        id=data["id"],
        question=data["question"],
        expected_terms=set(data.get("expected_terms", [])),
        required_citations=data.get("required_citations", True),
        should_refuse=data.get("should_refuse", False),
        notes=data.get("notes"),
    )


def _answer_candidate_from_json(data: dict[str, Any]) -> AnswerCandidate:
    return AnswerCandidate(
        answer=data.get("answer", ""),
        sources=[
            AnswerSource(
                source_id=source["source_id"],
                text=source["text"],
                relative_path=source.get("relative_path"),
            )
            for source in data.get("sources", [])
        ],
    )


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _report_is_stale(path: Path, expected: str, *, regenerate_hint: str) -> bool:
    if not path.exists():
        print(f"Report is missing: {path}", file=sys.stderr)
        return True
    current = path.read_text(encoding="utf-8")
    if current != expected:
        print(f"Report is stale: {regenerate_hint}", file=sys.stderr)
        return True
    return False


def _append_summary(path: Path, markdown: str) -> None:
    with path.open("a", encoding="utf-8") as summary:
        summary.write(markdown)
        summary.write("\n")


def _live_run_metadata(
    responses: list[SearchResponse],
    *,
    database_url: str | None,
    limit: int,
) -> dict[str, Any]:
    first_response = responses[0] if responses else None
    return {
        "mode": "live_search",
        "database_url": database_url or "configured default",
        "embedding_provider": (
            first_response.embedding_provider if first_response else "unknown"
        ),
        "embedding_model": first_response.embedding_model if first_response else "unknown",
        "embedding_dimensions": first_response.dimensions if first_response else "unknown",
        "limit": limit,
        "query_count": len(responses),
        "total_candidates_scored": sum(
            response.candidate_count for response in responses
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
