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

from librarian_evaluation.reporting import build_retrieval_report_document
from librarian_evaluation.retrieval import (
    RetrievalEvaluationCase,
    RetrievalResult,
    evaluate_retrieval_cases,
)

DEFAULT_BENCHMARK_PATH = REPO_ROOT / "tests/fixtures/evaluation/retrieval_benchmark.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs/evaluation-retrieval-report.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Librarian retrieval evaluation reports."
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
        "--check",
        action="store_true",
        help="Fail if the output file does not match the generated report.",
    )
    args = parser.parse_args()

    document = generate_report_document(args.benchmark)
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not args.output.exists():
            print(f"Report is missing: {args.output}", file=sys.stderr)
            return 1
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"Report is stale: run scripts/evaluate_retrieval.py --output {args.output}",
                file=sys.stderr,
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote retrieval evaluation report to {args.output}")
    return 0


def generate_report_document(benchmark_path: Path) -> dict[str, Any]:
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


if __name__ == "__main__":
    raise SystemExit(main())
