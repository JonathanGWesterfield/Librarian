#!/usr/bin/env python3
"""Developer CLI for generating, listing, and deleting book topic tags.

This script works with tags stored in the local Librarian SQLite database. It
does not ingest EPUBs and it does not create book summaries. Tag generation
requires that the target book already has a stored book summary for the selected
provider/model/detail combination. In this first pass, the CLI handles topic
tags only; genre classification is intentionally separate.

Use this when you want to inspect generated topics, rebuild tags after changing
the tag prompt or model, or delete generated tags before benchmarking another
provider. For destructive deletes, the command requires a specific book target.

Examples:

Generate topic tags for a book using an existing Codex summary:
    python3 scripts/tags.py \\
      --database-url sqlite:///data/librarian.db \\
      generate \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov" \\
      --source-summary-provider codex \\
      --source-summary-model codex \\
      --generation-provider codex \\
      --generation-model codex

Reset and rebuild tags with Ollama:
    python3 scripts/tags.py \\
      --database-url sqlite:///data/librarian.db \\
      generate \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov" \\
      --generation-provider ollama \\
      --generation-model llama3.2:3b \\
      --reset

List stored tags for one book:
    python3 scripts/tags.py \\
      --database-url sqlite:///data/librarian.db \\
      list \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov"

Delete generated topic tags for one book:
    python3 scripts/tags.py \\
      --database-url sqlite:///data/librarian.db \\
      delete \\
      --book-title "Forward the Foundation" \\
      --author "Isaac Asimov"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from librarian_config.config import (
    DATABASE_URL_ENV,
    GENERATION_MODEL_ENV,
    GENERATION_PROVIDER_ENV,
    OLLAMA_BASE_URL_ENV,
)
from librarian_metadata.tags import (
    DeleteBookTagsOptions,
    GenerateBookTagsOptions,
    ListBookTagsOptions,
    delete_book_tags,
    generate_book_tags,
    list_book_tags,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate, list, and delete Librarian book topic tags."
    )
    parser.add_argument(
        "--database-url",
        help=f"Override the local database instead of {DATABASE_URL_ENV}.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate or reuse topic tags from an existing book summary.",
    )
    _add_book_filters(generate_parser)
    _add_generation_options(generate_parser)
    generate_parser.add_argument(
        "--source-summary-provider",
        help="Provider for the stored book summary used as tag source.",
    )
    generate_parser.add_argument(
        "--source-summary-model",
        help="Model for the stored book summary used as tag source.",
    )
    generate_parser.add_argument(
        "--source-summary-detail",
        choices=["short", "medium", "detailed"],
        default="medium",
        help="Detail level for the stored book summary used as tag source.",
    )
    generate_parser.add_argument(
        "--max-tags",
        type=int,
        default=12,
        help="Maximum topic tags to generate.",
    )
    generate_parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Regenerate tags even when cached tags exist.",
    )
    generate_parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete matching generated topic tags before regenerating.",
    )
    generate_parser.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser(
        "list",
        help="List stored book tags, optionally scoped to one book.",
    )
    _add_book_filters(list_parser)
    _add_tag_filters(list_parser, include_provider_model=True)
    _add_json_flag(list_parser)

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete generated topic tags for one book.",
    )
    _add_book_filters(delete_parser)
    _add_tag_filters(delete_parser)
    _add_json_flag(delete_parser)

    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_book_tags(
                GenerateBookTagsOptions(
                    database_url=args.database_url,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    source_summary_provider=args.source_summary_provider,
                    source_summary_model=args.source_summary_model,
                    source_summary_detail=args.source_summary_detail,
                    generation_provider=args.generation_provider,
                    generation_model=args.generation_model,
                    ollama_base_url=args.ollama_base_url,
                    max_tags=args.max_tags,
                    force_refresh=args.force_refresh,
                    reset=args.reset,
                )
            )
            payload = result.to_dict()
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                _print_generated_tags(payload)
            return 0

        if args.command == "list":
            tags = list_book_tags(
                ListBookTagsOptions(
                    database_url=args.database_url,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    tag_type=args.tag_type,
                    source=args.source,
                    provider=args.provider,
                    model=args.model,
                )
            )
            payload = [asdict(tag) for tag in tags]
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                _print_tag_list(payload)
            return 0

        if args.command == "delete":
            deleted = delete_book_tags(
                DeleteBookTagsOptions(
                    database_url=args.database_url,
                    book_id=args.book_id,
                    book_title=args.book_title,
                    author=args.author,
                    tag_type=args.tag_type,
                    source=args.source,
                )
            )
            payload = {"deleted_tags": deleted}
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Deleted tags: {deleted}")
            return 0
    except (ValueError, NotImplementedError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    parser.error(f"unsupported command: {args.command}")
    return 2


def _add_book_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--book-id", help="Target one exact stored book id.")
    parser.add_argument("--book-title", help="Target a matching book title.")
    parser.add_argument("--author", help="Restrict title lookup to this author.")


def _add_generation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--generation-provider",
        choices=["noop", "ollama", "codex"],
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


def _add_tag_filters(
    parser: argparse.ArgumentParser, *, include_provider_model: bool = False
) -> None:
    parser.add_argument(
        "--tag-type",
        default="topic",
        help="Filter by tag type. Defaults to topic.",
    )
    parser.add_argument(
        "--source",
        default="llm",
        help="Filter by tag source. Defaults to llm.",
    )
    if include_provider_model:
        parser.add_argument("--provider", help="Filter listed tags by provider.")
        parser.add_argument("--model", help="Filter listed tags by model.")


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def _print_generated_tags(payload: dict[str, object]) -> None:
    print(f"Book: {payload['title'] or payload['book_id']}")
    print(f"Authors: {', '.join(payload['authors'])}")
    print(
        "Summary source: "
        f"{payload['source_summary_provider']} / {payload['source_summary_model']}"
    )
    print(
        "Tag generator: "
        f"{payload['generation_provider']} / {payload['generation_model']}"
    )
    print(
        "Tags: "
        f"{payload['generated_tags']} generated, "
        f"{payload['cached_tags']} cached"
    )
    if payload["deleted_tags"]:
        print(f"Deleted before rebuild: {payload['deleted_tags']}")
    _print_tag_list(payload["tags"])


def _print_tag_list(tags: object) -> None:
    if not isinstance(tags, list) or not tags:
        print("No tags found.")
        return
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        confidence = tag.get("confidence")
        confidence_text = "" if confidence is None else f" ({confidence:.2f})"
        prefix = tag.get("tag_type", "tag")
        source = tag.get("source", "unknown")
        provider = tag.get("provider")
        model = tag.get("model")
        provenance = f"{source}"
        if provider or model:
            provenance = f"{provenance}, {provider or '?'} / {model or '?'}"
        print(f"- [{prefix}] {tag['tag']}{confidence_text} - {provenance}")
        if tag.get("rationale"):
            print(f"  {tag['rationale']}")


if __name__ == "__main__":
    raise SystemExit(main())
