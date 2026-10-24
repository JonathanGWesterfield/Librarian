#!/usr/bin/env python3
"""Run one configuration-writing command while holding the Librarian lease."""

from __future__ import annotations

import argparse
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_config.write_lease import (  # noqa: E402
    ConfigurationWriteLeaseError,
    acquire_configuration_write_lease,
)


def _run_command_while_holding_lease(command: list[str], environment: dict[str, str]) -> int:
    """Run ``command`` without releasing the lease during signal cleanup.

    On Unix, the command owns a separate process group.  An interruption aimed
    at this helper is forwarded to that whole group, then this process waits
    for it to finish before leaving the lease context.  This lets shell traps
    restore a temporary configuration before another cooperating writer can
    acquire the lease.  Keep the existing Windows behavior: the PowerShell
    launcher only needs this helper to synchronously run one command there.
    """

    if os.name == "nt":  # pragma: no cover - exercised by the PowerShell launcher.
        return subprocess.run(command, env=environment, check=False).returncode

    child: subprocess.Popen[bytes] | None = None
    pending_signal: int | None = None

    def forward_signal_to_child_process_group(signum: int, _frame: object) -> None:
        nonlocal pending_signal
        pending_signal = signum
        if child is None or child.poll() is not None:
            return
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            # The command exited between poll() and killpg().  wait() below
            # still reaps it before the lease is released.
            pass

    previous_handlers = {
        signum: signal.signal(signum, forward_signal_to_child_process_group)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        child = subprocess.Popen(command, env=environment, start_new_session=True)
        if pending_signal is not None:
            forward_signal_to_child_process_group(pending_signal, None)
        return_code = child.wait()
        if pending_signal is not None:
            _wait_for_process_group_to_exit(child.pid)
        return return_code
    finally:
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)


def _wait_for_process_group_to_exit(process_group_id: int) -> None:
    """Wait until every member of an interrupted child process group exits."""

    while True:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return
        # This helper created the group, so a permission error is not expected.
        # Retain the lease instead of turning it into a write window if a host
        # changes that assumption while the interrupted command is cleaning up.
        except PermissionError:
            pass
        time.sleep(0.01)


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
            return _run_command_while_holding_lease(command, environment)
    except ConfigurationWriteLeaseError as error:
        print(f"[librarian] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
