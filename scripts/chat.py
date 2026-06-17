#!/usr/bin/env python3
"""Standalone local chat CLI for Librarian.

This is a temporary user-facing shell until a desktop frontend exists. It calls
the same chat service as the FastAPI endpoint: retrieve source chunks, ask the
configured local generator, and print the answer with sources.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.chat import ChatOptions, answer_question
from librarian_config.config import (
    DATABASE_URL_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_PROVIDER_ENV,
    GENERATION_MODEL_ENV,
    GENERATION_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask Librarian about local books.")
    parser.add_argument("question", nargs="*", help="Question to ask.")
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["noop", "ollama"],
        help=f"Embedding provider override instead of {EMBEDDING_PROVIDER_ENV}.",
    )
    parser.add_argument(
        "--embedding-model",
        help=f"Embedding model override instead of {EMBEDDING_MODEL_ENV}.",
    )
    parser.add_argument(
        "--generation-provider",
        choices=["noop", "ollama"],
        help=f"Generation provider override instead of {GENERATION_PROVIDER_ENV}.",
    )
    parser.add_argument(
        "--generation-model",
        help=f"Generation model override instead of {GENERATION_MODEL_ENV}.",
    )
    parser.add_argument(
        "--ollama-base-url",
        help=f"Ollama base URL override instead of {OLLAMA_BASE_URL_ENV}.",
    )
    parser.add_argument(
        "--retrieval-limit",
        type=int,
        default=30,
        help="Number of retrieved chunks to pass into the answer prompt.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    args = parser.parse_args(argv)

    question = " ".join(args.question).strip()
    if not question:
        if args.json:
            print("Error: --json requires a single question argument", file=sys.stderr)
            return 2
        return _interactive(args)

    return _ask_once(args, question)


def _interactive(args: argparse.Namespace) -> int:
    print("Librarian chat. Press Ctrl-D or enter an empty question to exit.")
    while True:
        try:
            question = input("\nQuestion: ").strip()
        except EOFError:
            print()
            return 0
        if not question:
            return 0
        exit_code = _ask_once(args, question)
        if exit_code != 0:
            return exit_code


def _ask_once(args: argparse.Namespace, question: str) -> int:
    try:
        result = answer_question(
            ChatOptions(
                question=question,
                database_url=args.database_url,
                embedding_provider=args.embedding_provider,
                embedding_model=args.embedding_model,
                generation_provider=args.generation_provider,
                generation_model=args.generation_model,
                ollama_base_url=args.ollama_base_url,
                retrieval_limit=args.retrieval_limit,
            )
        )
    except (ValueError, NotImplementedError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_chat(payload)
    return 0


def _print_chat(payload: dict[str, object]) -> None:
    print("\nAnswer:")
    print(payload["answer"])
    print()
    print(
        "Models: "
        f"embedding={payload['embedding_provider']}/{payload['embedding_model']}, "
        f"generation={payload['generation_provider']}/{payload['generation_model']}"
    )
    print(f"Candidates scored: {payload['candidate_count']}")
    print()
    print("Sources:")
    sources = payload["sources"]
    if not isinstance(sources, list) or not sources:
        print("- none")
        return
    for source in sources:
        if not isinstance(source, dict):
            continue
        title = source["title"] or source["relative_path"]
        print(
            f"- [{source['source_id']}] score={float(source['score']):.4f} "
            f"{title} ({source['relative_path']} chunk {source['chunk_index']})"
        )


if __name__ == "__main__":
    raise SystemExit(main())
