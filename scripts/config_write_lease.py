#!/usr/bin/env python3
"""Run one configuration-writing command while holding the Librarian lease."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_config.write_lease import (  # noqa: E402
    ConfigurationWriteLeaseError,
    acquire_configuration_write_lease,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--copy-file", nargs=2, metavar=("SOURCE", "DESTINATION"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.copy_file is not None and command:
        parser.error("--copy-file cannot be combined with a command")
    if args.copy_file is None and not command:
        parser.error("--copy-file or a command after -- is required")
    try:
        with acquire_configuration_write_lease(args.root):
            if args.copy_file is not None:
                source, destination = (Path(value) for value in args.copy_file)
                shutil.copy2(source, destination)
                return 0
            environment = {**os.environ, "LIBRARIAN_CONFIG_WRITE_LEASE_HELD": "1"}
            return subprocess.run(command, env=environment, check=False).returncode
    except ConfigurationWriteLeaseError as error:
        print(f"[librarian] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
