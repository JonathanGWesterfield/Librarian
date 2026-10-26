#!/usr/bin/env python3
"""Validate and refresh the answer-delivery task-ledger freshness record.

The task ledger is derived from the canonical roadmap, technical design, ADR,
compatibility plan, and acceptance charter.  A checked-in digest records the
exact source set that its task anchors were last reviewed against.  This script
fails when either the source set or a local task anchor has drifted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = REPOSITORY_ROOT / "docs/tasks/answer-delivery"
MANIFEST_PATH = TASK_ROOT / "freshness.json"
CANONICAL_SOURCES = (
    Path("docs/answer-delivery/README.md"),
    Path("docs/answer-delivery/technical-design.md"),
    Path("docs/answer-delivery/adr-internal-rpc-transport.md"),
    Path("docs/answer-delivery/compatibility-and-migration.md"),
    Path("docs/answer-delivery/acceptance.md"),
)
LIFECYCLES = {"planned", "claimed", "in progress", "in review", "blocked", "complete"}
REQUIRED_SECTIONS = (
    "## Immutable scope and goal",
    "## Prerequisite task IDs and ordered dependencies",
    "## Execution class, owned paths, and forbidden paths",
    "## Design anchors",
    "## Acceptance criteria",
    "## Required tests and evidence",
    "## Append-only log, artifacts, and notes",
    "## Handoff",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def github_heading_slug(heading: str) -> str:
    """Return the GitHub-style anchor used by this repository's headings."""

    clean = re.sub(r"<[^>]+>", "", heading.strip().lower())
    clean = re.sub(r"[^\w\- ]", "", clean)
    return re.sub(r" +", "-", clean)


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            anchors.add(github_heading_slug(match.group(1)))
    return anchors


def task_files() -> list[Path]:
    return sorted(
        path
        for path in TASK_ROOT.glob("M*/*.md")
        if path.name != "README.md"
    )


def task_ids() -> set[str]:
    ids: set[str] = set()
    for path in task_files():
        match = re.search(r"\*\*Task ID:\*\* `([^`]+)`", path.read_text(encoding="utf-8"))
        if match:
            ids.add(match.group(1))
    return ids


def validate_task(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"missing required section: {section}")
    if "**Read first — [program outcome]" not in text:
        errors.append("missing high-level Read first anchors")
    direct = re.search(
        r"\*\*Direct requirements for this task:\*\*\n(.*?)(?=\n## Acceptance criteria)",
        text,
        flags=re.DOTALL,
    )
    if direct is None or not re.search(r"^- \[[^]]+\]\([^)]+\)", direct.group(1), flags=re.MULTILINE):
        errors.append("missing direct design-requirement anchors")
    lifecycle = re.search(r"\*\*Lifecycle status:\*\* \*\*([^*]+)\*\*", text)
    if lifecycle is None or lifecycle.group(1) not in LIFECYCLES:
        errors.append("missing or invalid lifecycle status")
    if not re.search(r"\*\*Task ID:\*\* `AD-M\d\d-\d\d`", text):
        errors.append("missing stable task ID")
    return errors


def validate_markdown_links(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"(?<!\!)\[[^]]+\]\(([^)]+)\)", text):
        if target.startswith(("http:", "https:", "mailto:")):
            continue
        target = target.split(' "', 1)[0]
        relative, _, anchor = target.partition("#")
        resolved = (path.parent / relative).resolve() if relative else path.resolve()
        if relative and not resolved.exists():
            errors.append(f"missing target: {target}")
            continue
        if anchor and resolved.suffix == ".md" and resolved.exists() and anchor not in markdown_anchors(resolved):
            errors.append(f"missing anchor: {target}")
    return errors


def source_hashes() -> dict[str, str]:
    return {str(path): sha256(REPOSITORY_ROOT / path) for path in CANONICAL_SOURCES}


def load_manifest() -> dict[str, object]:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("freshness manifest is missing; run with --refresh after reviewing impacted tasks") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"freshness manifest is invalid JSON: {error}") from error


def check() -> int:
    errors: list[str] = []
    paths = [*task_files(), TASK_ROOT / "README.md", TASK_ROOT.parent / "README.md"]
    for path in task_files():
        for error in validate_task(path):
            errors.append(f"{path.relative_to(REPOSITORY_ROOT)}: {error}")
    for path in paths:
        for error in validate_markdown_links(path):
            errors.append(f"{path.relative_to(REPOSITORY_ROOT)}: {error}")
    try:
        manifest = load_manifest()
    except ValueError as error:
        errors.append(str(error))
    else:
        if manifest.get("schema_version") != 1:
            errors.append("freshness manifest must use schema_version 1")
        recorded = manifest.get("canonical_source_sha256")
        if recorded != source_hashes():
            errors.append(
                "canonical answer-delivery sources changed since the task ledger was reviewed; "
                "update every affected task's direct anchors/scope and refresh the manifest"
            )
        review = manifest.get("last_freshness_review")
        if not isinstance(review, dict) or not review.get("reviewed_by") or not review.get("task_ids") or not review.get("note"):
            errors.append("freshness manifest lacks reviewer, affected task IDs, or review note")
        elif not set(review["task_ids"]).issubset(task_ids()):
            errors.append("freshness manifest names an unknown task ID")
    if errors:
        for error in errors:
            print(f"[task-ledger] {error}", file=sys.stderr)
        return 1
    print(f"Task ledger is fresh: {len(task_files())} task files and canonical design sources match.")
    return 0


def refresh(args: argparse.Namespace) -> int:
    available_ids = task_ids()
    selected_ids = set(args.task_id)
    if not args.reviewed_by.strip() or not args.note.strip() or not selected_ids:
        raise ValueError("--refresh requires --reviewed-by, --note, and at least one --task-id")
    unknown = selected_ids - available_ids
    if unknown:
        raise ValueError(f"unknown task IDs: {', '.join(sorted(unknown))}")
    manifest = {
        "schema_version": 1,
        "canonical_source_sha256": source_hashes(),
        "last_freshness_review": {
            "reviewed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "reviewed_by": args.reviewed_by.strip(),
            "task_ids": sorted(selected_ids),
            "note": args.note.strip(),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Refreshed {MANIFEST_PATH.relative_to(REPOSITORY_ROOT)} for {len(selected_ids)} reviewed task(s).")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="record a completed freshness review")
    parser.add_argument("--reviewed-by", default="", help="person or agent accountable for the review")
    parser.add_argument("--task-id", action="append", default=[], help="affected task ID; repeat for each reviewed task")
    parser.add_argument("--note", default="", help="brief reason and scope of the freshness review")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return refresh(args) if args.refresh else check()
    except ValueError as error:
        print(f"[task-ledger] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
