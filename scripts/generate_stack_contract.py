"""Generate or verify immutable release metadata for the broker handshake.

The caller supplies the clean, committed release SHA. This script does not infer
one from the checkout because a build pipeline is responsible for proving that
the supplied release is clean before it packages the manifest into every image.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESCRIPTOR = Path("proto/librarian/answer/v1/answer_delivery.pb")
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.stack_contract import (
    DEFAULT_CONTRACT_MINOR,
    StackContractError,
    build_stack_contract,
    serialize_stack_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stack-release-sha",
        required=True,
        help="Clean, committed 40-character lowercase Git SHA for this release.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write or verify librarian-stack-contract.json.",
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=REPO_ROOT / DEFAULT_DESCRIPTOR,
        help="Canonical raw protobuf descriptor (default: %(default)s).",
    )
    parser.add_argument(
        "--contract-minor",
        type=int,
        default=DEFAULT_CONTRACT_MINOR,
        help="v1 contract minor recorded in the manifest (default: %(default)s).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail unless the existing output exactly matches the generated manifest.",
    )
    args = parser.parse_args()

    try:
        contract = build_stack_contract(
            stack_release_sha=args.stack_release_sha,
            descriptor=args.descriptor.read_bytes(),
            contract_minor=args.contract_minor,
        )
    except (OSError, StackContractError) as error:
        parser.error(str(error))
    expected = serialize_stack_contract(contract)

    if args.check:
        try:
            actual = args.output.read_text(encoding="utf-8")
        except OSError as error:
            print(f"Could not read {args.output}: {error}", file=sys.stderr)
            return 1
        if actual != expected:
            print(
                f"{args.output} does not match the canonical stack contract; rerun "
                "scripts/generate_stack_contract.py.",
                file=sys.stderr,
            )
            return 1
        print(f"Stack contract is current: {args.output}")
        return 0

    _atomic_write(args.output, expected)
    print(f"Generated stack contract: {args.output}")
    return 0


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(contents)
        Path(temporary_path).replace(path)
    except BaseException:
        Path(temporary_path).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
