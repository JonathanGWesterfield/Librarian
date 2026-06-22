#!/usr/bin/env python3
"""Generate Librarian retrieval and answer-quality evaluation reports.

This script is the main evaluation runner for CI and local benchmarking. It can
run deterministic fixture-based checks, live retrieval against the local SQLite
database, live answer generation through the current chat stack, optional
LLM-as-judge scoring, and run-over-run comparison metadata. It writes both
machine-readable JSON and human-readable Markdown reports.

Use this when you want to measure whether retrieval or answer changes are
actually improving quality. The default mode is safe for CI because it runs
against checked-in smoke fixtures. Live modes require an ingested local database
and, for non-noop providers, the corresponding local services.

Examples:

Run the deterministic CI-style report and fail if thresholds are missed:
    python3 scripts/evaluate_retrieval.py --check

Generate deterministic JSON and Markdown reports:
    python3 scripts/evaluate_retrieval.py \\
      --output docs/evaluation-retrieval-report.json \\
      --markdown-output docs/evaluation-report.md

Run live retrieval against the local SQLite database:
    python3 scripts/evaluate_retrieval.py \\
      --live \\
      --database-url sqlite:///data/librarian.db \\
      --embedding-provider ollama \\
      --embedding-model all-minilm

Run live answer evaluation with Codex as the generator and LLM judge:
    python3 scripts/evaluate_retrieval.py \\
      --live \\
      --live-answers \\
      --llm-judge \\
      --database-url sqlite:///data/librarian.db \\
      --generation-provider codex \\
      --generation-model codex
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.chat import ChatOptions, ChatResponse, answer_question
from librarian_evaluation.comparison import compare_report_documents
from librarian_evaluation.llm_judge import (
    LLMJudge,
    create_judge,
    evaluate_answers_with_llm_judge,
)
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
from librarian_logging import configure_cli_logging
from librarian_search.search import SearchOptions, SearchResponse, search_chunks

logger = logging.getLogger(__name__)

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
DEFAULT_GOLDEN_ANSWER_CORPUS_PATH = (
    REPO_ROOT / "tests/fixtures/evaluation/golden_answer_quality_corpus.json"
)


def main() -> int:
    configure_cli_logging()
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
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
        "--live-answers",
        action="store_true",
        help="Run the live chat stack against the answer-quality corpus.",
    )
    parser.add_argument(
        "--answer-corpus",
        type=Path,
        default=DEFAULT_GOLDEN_ANSWER_CORPUS_PATH,
        help="Path to the live answer-quality corpus JSON file.",
    )
    parser.add_argument(
        "--github-summary",
        type=Path,
        default=None,
        help="Optional path, usually GITHUB_STEP_SUMMARY, to append Markdown output.",
    )
    parser.add_argument(
        "--record-run-metadata",
        action="store_true",
        help=(
            "Include elapsed time and git metadata in written reports. "
            "Live reports include this automatically."
        ),
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        default=None,
        help="Optional prior report JSON to compare against in written output.",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Score answer quality with an LLM judge. Defaults to Codex with Ollama fallback.",
    )
    parser.add_argument(
        "--judge-provider",
        default="codex",
        help="LLM judge provider. Supported values: codex, ollama.",
    )
    parser.add_argument(
        "--judge-model",
        default="codex",
        help="LLM judge model name.",
    )
    parser.add_argument(
        "--judge-fallback-provider",
        default="ollama",
        help="Fallback LLM judge provider. Use 'none' to disable fallback.",
    )
    parser.add_argument(
        "--judge-fallback-model",
        default=None,
        help="Fallback LLM judge model. Defaults to --generation-model or llama3.2:3b.",
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
        "--generation-provider",
        default=None,
        help="Generation provider for live answer-quality evaluation.",
    )
    parser.add_argument(
        "--generation-model",
        default=None,
        help="Generation model for live answer-quality evaluation.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum live search results to score per golden corpus query.",
    )
    parser.add_argument(
        "--retrieval-limit",
        type=int,
        default=30,
        help="Maximum retrieved chunks sent to chat during live answer evaluation.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output file does not match the generated report.",
    )
    args = parser.parse_args()
    judge = _create_optional_judge(
        enabled=args.llm_judge,
        provider=args.judge_provider,
        model=args.judge_model,
        ollama_base_url=args.ollama_base_url,
    )
    fallback_judge = _create_optional_fallback_judge(
        enabled=args.llm_judge,
        provider=args.judge_fallback_provider,
        model=args.judge_fallback_model or args.generation_model or "llama3.2:3b",
        ollama_base_url=args.ollama_base_url,
    )

    if args.live:
        if args.output == DEFAULT_OUTPUT_PATH:
            args.output = DEFAULT_LIVE_OUTPUT_PATH
        if args.markdown_output == DEFAULT_MARKDOWN_OUTPUT_PATH:
            args.markdown_output = DEFAULT_LIVE_MARKDOWN_OUTPUT_PATH
        document = generate_live_report_document(
            args.golden_corpus,
            answer_benchmark_path=args.answer_benchmark,
            live_answer_corpus_path=args.answer_corpus,
            live_answers=args.live_answers,
            database_url=args.database_url,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            generation_provider=args.generation_provider,
            generation_model=args.generation_model,
            ollama_base_url=args.ollama_base_url,
            limit=args.limit,
            retrieval_limit=args.retrieval_limit,
            judge=judge,
            fallback_judge=fallback_judge,
        )
    else:
        document = generate_report_document(
            args.benchmark,
            answer_benchmark_path=args.answer_benchmark,
            judge=judge,
            fallback_judge=fallback_judge,
        )
    should_record_run_metadata = args.live or args.record_run_metadata
    output_document = (
        _with_execution_metadata(document, started_at, started_perf)
        if should_record_run_metadata
        else document
    )
    summary_document = (
        _with_execution_metadata(document, started_at, started_perf)
        if args.github_summary
        else output_document
    )
    output_document = _with_comparison(output_document, args.compare_to)
    summary_document = _with_comparison(summary_document, args.compare_to)
    golden_corpus = _load_optional_json(args.golden_corpus)
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    rendered_markdown = render_evaluation_markdown(
        document,
        golden_corpus=golden_corpus,
    )
    output_rendered = json.dumps(output_document, indent=2, sort_keys=True) + "\n"
    output_rendered_markdown = render_evaluation_markdown(
        output_document,
        golden_corpus=golden_corpus,
    )
    summary_markdown = render_evaluation_markdown(
        summary_document,
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
            _append_summary(args.github_summary, summary_markdown)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_rendered, encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(output_rendered_markdown, encoding="utf-8")
    if args.github_summary:
        _append_summary(args.github_summary, summary_markdown)
    logger.info("Wrote retrieval evaluation report to %s", args.output)
    logger.info("Wrote human-readable evaluation report to %s", args.markdown_output)
    return 0


def generate_report_document(
    benchmark_path: Path,
    *,
    answer_benchmark_path: Path | None = None,
    judge: LLMJudge | None = None,
    fallback_judge: LLMJudge | None = None,
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
    answer_quality = _answer_report_from_path(answer_benchmark_path)
    llm_judge = _llm_judge_report_from_answer_benchmark(
        answer_benchmark_path,
        judge=judge,
        fallback_judge=fallback_judge,
    )
    document = build_retrieval_report_document(
        report,
        benchmark=benchmark,
        primary_k=benchmark_data.get("primary_k"),
        answer_quality=answer_quality,
        llm_judge=llm_judge,
    )
    return document.to_dict()


def generate_live_report_document(
    corpus_path: Path,
    *,
    answer_benchmark_path: Path | None = None,
    live_answer_corpus_path: Path | None = None,
    live_answers: bool = False,
    database_url: str | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    generation_provider: str | None = None,
    generation_model: str | None = None,
    ollama_base_url: str | None = None,
    limit: int = 10,
    retrieval_limit: int = 30,
    search_fn=search_chunks,
    answer_fn=answer_question,
    judge: LLMJudge | None = None,
    fallback_judge: LLMJudge | None = None,
) -> dict[str, Any]:
    corpus_data = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = [_case_from_json(case) for case in corpus_data["cases"]]
    ranked_results_by_case: dict[str, list] = {}
    responses: list[SearchResponse] = []
    search_latencies_seconds: list[float] = []

    for case in cases:
        search_started = time.perf_counter()
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
        search_latencies_seconds.append(time.perf_counter() - search_started)
        responses.append(response)
        ranked_results_by_case[case.id] = response.results

    benchmark = dict(corpus_data.get("benchmark", {}))
    benchmark["mode"] = "live_search"
    report = evaluate_retrieval_cases(
        cases,
        ranked_results_by_case,
        k_values=corpus_data.get("k_values"),
    )
    run_metadata = _live_run_metadata(
        responses,
        database_url=database_url,
        limit=limit,
        search_latencies_seconds=search_latencies_seconds,
    )
    answer_quality = _answer_report_from_path(answer_benchmark_path)
    llm_judge = _llm_judge_report_from_answer_benchmark(
        answer_benchmark_path,
        judge=judge,
        fallback_judge=fallback_judge,
    )
    if live_answers:
        (
            answer_quality,
            answer_run_metadata,
            answer_cases,
            answer_candidates,
        ) = _live_answer_report_from_path(
            live_answer_corpus_path,
            database_url=database_url,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            generation_provider=generation_provider,
            generation_model=generation_model,
            ollama_base_url=ollama_base_url,
            retrieval_limit=retrieval_limit,
            answer_fn=answer_fn,
        )
        run_metadata["answer_quality"] = answer_run_metadata
        if judge is not None:
            llm_judge = evaluate_answers_with_llm_judge(
                answer_cases,
                answer_candidates,
                judge=judge,
                fallback_judge=fallback_judge,
            )

    document = build_retrieval_report_document(
        report,
        benchmark=benchmark,
        primary_k=corpus_data.get("primary_k"),
        run=run_metadata,
        answer_quality=answer_quality,
        llm_judge=llm_judge,
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
    benchmark_data, cases, candidates = _answer_cases_and_candidates_from_path(path)
    generated_at = benchmark_data.get("benchmark", {}).get("generated_at")
    return evaluate_answer_cases(cases, candidates, generated_at=generated_at)


def _llm_judge_report_from_answer_benchmark(
    path: Path | None,
    *,
    judge: LLMJudge | None,
    fallback_judge: LLMJudge | None,
):
    if judge is None or path is None or not path.exists():
        return None
    _, cases, candidates = _answer_cases_and_candidates_from_path(path)
    return evaluate_answers_with_llm_judge(
        cases,
        candidates,
        judge=judge,
        fallback_judge=fallback_judge,
    )


def _answer_cases_and_candidates_from_path(path: Path):
    benchmark_data = json.loads(path.read_text(encoding="utf-8"))
    cases = [_answer_case_from_json(case) for case in benchmark_data["cases"]]
    candidates = {
        case["id"]: _answer_candidate_from_json(case)
        for case in benchmark_data["cases"]
    }
    return benchmark_data, cases, candidates


def _live_answer_report_from_path(
    path: Path | None,
    *,
    database_url: str | None,
    embedding_provider: str | None,
    embedding_model: str | None,
    generation_provider: str | None,
    generation_model: str | None,
    ollama_base_url: str | None,
    retrieval_limit: int,
    answer_fn=answer_question,
):
    if path is None or not path.exists():
        raise FileNotFoundError(
            "Live answer evaluation requires an answer corpus. "
            f"Missing path: {path}"
        )

    corpus_data = json.loads(path.read_text(encoding="utf-8"))
    cases = [_answer_case_from_json(case) for case in corpus_data["cases"]]
    responses: list[ChatResponse] = []
    candidates: dict[str, AnswerCandidate] = {}
    answer_latencies_seconds: list[float] = []

    for case in cases:
        answer_started = time.perf_counter()
        response = answer_fn(
            ChatOptions(
                question=case.question,
                database_url=database_url,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                generation_provider=generation_provider,
                generation_model=generation_model,
                ollama_base_url=ollama_base_url,
                retrieval_limit=retrieval_limit,
            )
        )
        answer_latencies_seconds.append(time.perf_counter() - answer_started)
        responses.append(response)
        candidates[case.id] = AnswerCandidate(
            answer=response.answer,
            sources=[
                AnswerSource(
                    source_id=source.source_id,
                    text=source.text,
                    relative_path=source.relative_path,
                )
                for source in response.sources
            ],
        )

    generated_at = corpus_data.get("benchmark", {}).get("generated_at")
    return (
        evaluate_answer_cases(cases, candidates, generated_at=generated_at),
        _live_answer_run_metadata(
            responses,
            corpus_path=path,
            retrieval_limit=retrieval_limit,
            answer_latencies_seconds=answer_latencies_seconds,
        ),
        cases,
        candidates,
    )


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


def _create_optional_judge(
    *,
    enabled: bool,
    provider: str,
    model: str,
    ollama_base_url: str | None,
) -> LLMJudge | None:
    if not enabled:
        return None
    return create_judge(
        provider,
        model=model,
        ollama_base_url=ollama_base_url or "http://localhost:11434",
    )


def _create_optional_fallback_judge(
    *,
    enabled: bool,
    provider: str,
    model: str,
    ollama_base_url: str | None,
) -> LLMJudge | None:
    if not enabled or provider.strip().casefold() == "none":
        return None
    return create_judge(
        provider,
        model=model,
        ollama_base_url=ollama_base_url or "http://localhost:11434",
    )


def _with_comparison(
    document: dict[str, Any],
    compare_to_path: Path | None,
) -> dict[str, Any]:
    if compare_to_path is None or not compare_to_path.exists():
        return document

    baseline = json.loads(compare_to_path.read_text(encoding="utf-8"))
    enriched = copy.deepcopy(document)
    enriched["comparison"] = compare_report_documents(
        enriched,
        baseline,
        baseline_label=str(compare_to_path),
    )
    return enriched


def _report_is_stale(path: Path, expected: str, *, regenerate_hint: str) -> bool:
    if not path.exists():
        logger.error("Report is missing: %s", path)
        return True
    current = path.read_text(encoding="utf-8")
    if current != expected:
        logger.error("Report is stale: %s", regenerate_hint)
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
    search_latencies_seconds: list[float],
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
        "search_total_seconds": _rounded_seconds(sum(search_latencies_seconds)),
        "search_mean_seconds": _mean_seconds(search_latencies_seconds),
        "search_max_seconds": _rounded_seconds(
            max(search_latencies_seconds, default=0.0)
        ),
    }


def _live_answer_run_metadata(
    responses: list[ChatResponse],
    *,
    corpus_path: Path,
    retrieval_limit: int,
    answer_latencies_seconds: list[float],
) -> dict[str, Any]:
    first_response = responses[0] if responses else None
    return {
        "mode": "live_chat",
        "corpus_path": str(corpus_path),
        "embedding_provider": (
            first_response.embedding_provider if first_response else "unknown"
        ),
        "embedding_model": first_response.embedding_model if first_response else "unknown",
        "generation_provider": (
            first_response.generation_provider if first_response else "unknown"
        ),
        "generation_model": first_response.generation_model if first_response else "unknown",
        "retrieval_limit": retrieval_limit,
        "question_count": len(responses),
        "total_candidates_scored": sum(
            response.candidate_count for response in responses
        ),
        "total_sources_returned": sum(len(response.sources) for response in responses),
        "answer_total_seconds": _rounded_seconds(sum(answer_latencies_seconds)),
        "answer_mean_seconds": _mean_seconds(answer_latencies_seconds),
        "answer_max_seconds": _rounded_seconds(
            max(answer_latencies_seconds, default=0.0)
        ),
    }


def _with_execution_metadata(
    document: dict[str, Any],
    started_at: datetime,
    started_perf: float,
) -> dict[str, Any]:
    enriched = copy.deepcopy(document)
    run = dict(enriched.get("run", {}))
    run["execution"] = {
        "started_at": started_at.isoformat(),
        "elapsed_seconds": _rounded_seconds(time.perf_counter() - started_perf),
    }
    run["git"] = _git_metadata()
    enriched["run"] = run
    return enriched


def _git_metadata() -> dict[str, Any]:
    return {
        "commit": _git_output("rev-parse", "HEAD") or "unknown",
        "short_commit": _git_output("rev-parse", "--short", "HEAD") or "unknown",
        "branch": _git_output("branch", "--show-current") or "unknown",
        "dirty": _git_dirty(),
    }


def _git_output(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _git_dirty() -> bool | str:
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return bool(completed.stdout.strip())


def _mean_seconds(values: list[float]) -> float:
    if not values:
        return 0.0
    return _rounded_seconds(sum(values) / len(values))


def _rounded_seconds(value: float) -> float:
    return round(value, 4)


if __name__ == "__main__":
    raise SystemExit(main())
