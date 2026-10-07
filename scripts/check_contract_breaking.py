"""Fail when the v1 broker descriptor changes incompatibly from a Git base."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from google.protobuf import descriptor_pb2

REPO_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_PATH = Path("proto/librarian/answer/v1/answer_delivery.pb")
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.compatibility import find_breaking_changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--against",
        default=os.environ.get("LIBRARIAN_CONTRACT_BASE_REF", "origin/main"),
        help="Git revision containing the released descriptor (default: origin/main).",
    )
    args = parser.parse_args()

    previous = _descriptor_at_revision(args.against)
    current = _descriptor_from_bytes((REPO_ROOT / DESCRIPTOR_PATH).read_bytes())
    changes = find_breaking_changes(previous, current)
    if changes:
        print(
            f"Breaking answer-delivery contract changes against {args.against}:",
            file=sys.stderr,
        )
        for change in changes:
            print(f"- {change}", file=sys.stderr)
        return 1

    print(f"Answer-delivery contract is compatible with {args.against}.")
    return 0


def _descriptor_at_revision(revision: str) -> descriptor_pb2.FileDescriptorProto:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{DESCRIPTOR_PATH.as_posix()}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(
            f"Could not read {DESCRIPTOR_PATH} from {revision}: {detail or 'unknown Git error'}"
        )
    return _descriptor_from_bytes(completed.stdout)


def _descriptor_from_bytes(raw: bytes) -> descriptor_pb2.FileDescriptorProto:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    descriptor_set.ParseFromString(raw)
    if len(descriptor_set.file) != 1:
        raise SystemExit("Expected exactly one answer-delivery file descriptor.")
    return descriptor_set.file[0]


if __name__ == "__main__":
    raise SystemExit(main())
