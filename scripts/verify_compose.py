#!/usr/bin/env python3
"""Exercise the runtime API through the full Compose verification stack.

The script ingests the rights-safe committed EPUB fixture through the runtime
API, indexes its embeddings into Compose OpenSearch, then evaluates the runtime
API's ``/search/hybrid`` endpoint. It deliberately does not read local books or
the developer's ``data/`` directory.

Examples:
    scripts/run_compose_verification.sh

    python3 scripts/verify_compose.py --api-url http://localhost:8000 \\
      --books-dir tests/fixtures/epubs --database-url sqlite:///data/librarian.db \\
      --opensearch-url http://localhost:9200 --ollama-base-url http://localhost:11434

    python3 scripts/verify_compose.py --help
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_search.opensearch import OpenSearchIndexOptions, index_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify hybrid retrieval through the runtime Compose API."
    )
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--books-dir", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--opensearch-url", required=True)
    parser.add_argument("--ollama-base-url", required=True)
    parser.add_argument("--embedding-provider", default="ollama")
    parser.add_argument("--embedding-model", default="all-minilm")
    args = parser.parse_args(argv)

    _post_json(
        f"{args.api_url.rstrip('/')}/ingestion/run",
        {
            "books_dir": args.books_dir,
            "embed_chunks": True,
            "embedding_provider": args.embedding_provider,
            "embedding_model": args.embedding_model,
            "ollama_base_url": args.ollama_base_url,
        },
    )
    index_result = index_chunks(
        OpenSearchIndexOptions(
            database_url=args.database_url,
            opensearch_url=args.opensearch_url,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            reset=True,
        )
    )
    if index_result.documents_indexed < 1:
        raise RuntimeError("The verification fixture produced no OpenSearch documents")

    report_path = Path("/tmp/librarian-compose-verification.json")
    markdown_path = Path("/tmp/librarian-compose-verification.md")
    command = [
        sys.executable,
        "scripts/evaluate_retrieval.py",
        "--live",
        "--api-url",
        args.api_url,
        "--golden-corpus",
        "tests/fixtures/evaluation/compose_retrieval_corpus.json",
        "--output",
        str(report_path),
        "--markdown-output",
        str(markdown_path),
        "--embedding-provider",
        args.embedding_provider,
        "--embedding-model",
        args.embedding_model,
        "--ollama-base-url",
        args.ollama_base_url,
    ]
    subprocess.run(command, check=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    hit_rate = report["retrieval"]["aggregate"]["hit_rate_at_k"]["1"]
    if hit_rate != 1.0:
        raise RuntimeError(f"Compose hybrid verification hit@1 was {hit_rate}, expected 1.0")
    print("[librarian] Compose runtime API hybrid verification passed (Hit@1: 1.0).")
    return 0


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=120) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Runtime API request failed ({exc.code}): {detail}") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("Runtime API returned an unexpected response")
    return decoded


if __name__ == "__main__":
    raise SystemExit(main())
