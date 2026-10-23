"""Validate and atomically back up local inputs before an R2 Compose cutover.

This command does not start, stop, build, or recreate Compose services.  It
requires a clean Git release, renders the full R2 Compose topology for the
security policy, validates the user-owned Docker-broker configuration and all
five role-specific credential files, then creates one owner-only backup.

Example:
    python3 scripts/prepare_r2_cutover.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(SCRIPT_DIRECTORY))

from librarian_config.config import LibrarianConfigError, get_librarian_config
from librarian_contracts.compose_security import (
    ComposeSecurityPolicyError,
    validate_r2_compose_security,
)

from resolve_provider_config import (
    BROKER_SECRET_NAMES,
    R2_BROKER_SECRET_ROLES,
    validate_r2_broker_secret_sources,
)

R2_PROFILES = ("codex-broker", "workers", "metadata-workers", "evaluation")
R2_BACKUP_PREFIX = "r2-cutover-"


class R2CutoverPreflightError(ValueError):
    """The local inputs are not safe to use for an atomic R2 cutover."""


@dataclass(frozen=True)
class R2CutoverBackup:
    """The release and local snapshot produced by a successful preparation."""

    release_sha: str
    path: Path


def prepare_r2_cutover(
    *,
    repository_root: Path,
    config_path: Path,
    backup_root: Path,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> R2CutoverBackup:
    """Prove all local cutover prerequisites and publish one atomic snapshot.

    The backup is intentionally the final step.  A missing secret, invalid
    configuration, dirty release, or non-conforming Compose topology therefore
    cannot leave a partial configuration/credential backup behind.
    """

    repository_root = repository_root.resolve()
    # Preserve symlink information for operator-controlled files.  A symlinked
    # secret/configuration source or backup root is not an atomic local
    # cutover input, so the readers below must be able to reject it.
    config_path = config_path.absolute()
    backup_root = backup_root.absolute()
    release_sha = _require_clean_release(repository_root)
    config_bytes = _read_regular_file(config_path, "configuration")

    try:
        config = get_librarian_config(config_path)
        validate_r2_broker_secret_sources(config)
    except LibrarianConfigError as error:
        raise R2CutoverPreflightError("R2 configuration or credential sources are invalid") from error

    _validate_r2_compose_topology(repository_root, release_sha)
    secret_bytes = {
        role: _read_regular_file(
            config_path.parent / "secrets" / BROKER_SECRET_NAMES[role],
            "role-specific credential",
        )
        for role in R2_BROKER_SECRET_ROLES
    }
    backup_path = _backup_path(backup_root, release_sha, now())
    _write_atomic_backup(
        backup_path=backup_path,
        config_bytes=config_bytes,
        secret_bytes=secret_bytes,
    )
    return R2CutoverBackup(release_sha=release_sha, path=backup_path)


def _require_clean_release(repository_root: Path) -> str:
    top_level = _run_checked(
        ["git", "-C", str(repository_root), "rev-parse", "--show-toplevel"],
        "could not identify the Git release root",
    ).strip()
    if Path(top_level).resolve() != repository_root:
        raise R2CutoverPreflightError("repository root must be the Git release root")
    release_sha = _run_checked(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        "could not identify the Git release SHA",
    ).strip()
    if len(release_sha) != 40 or any(
        character not in "0123456789abcdef" for character in release_sha
    ):
        raise R2CutoverPreflightError("Git release SHA must be a committed lowercase 40-character SHA")
    status = _run_checked(
        [
            "git",
            "-C",
            str(repository_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        "could not verify whether the Git release is clean",
    )
    if status:
        raise R2CutoverPreflightError("R2 cutover requires a clean Git release checkout")
    return release_sha


def _validate_r2_compose_topology(repository_root: Path, release_sha: str) -> None:
    command = ["docker", "compose"]
    for profile in R2_PROFILES:
        command.extend(("--profile", profile))
    command.extend(
        (
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.r2.yml",
            "config",
            "--format",
            "json",
        )
    )
    environment = {**os.environ, "LIBRARIAN_STACK_RELEASE_SHA": release_sha}
    try:
        rendered = subprocess.run(
            command,
            cwd=repository_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise R2CutoverPreflightError(
            "Docker Compose is required to validate the R2 topology"
        ) from error
    if rendered.returncode != 0:
        raise R2CutoverPreflightError("Docker Compose could not render the R2 topology")
    try:
        compose = json.loads(rendered.stdout)
        validate_r2_compose_security(compose)
    except (json.JSONDecodeError, ComposeSecurityPolicyError) as error:
        raise R2CutoverPreflightError(
            "rendered R2 Compose topology violates the cutover policy"
        ) from error


def _run_checked(command: Sequence[str], failure_message: str) -> str:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as error:
        raise R2CutoverPreflightError(failure_message) from error
    if completed.returncode != 0:
        raise R2CutoverPreflightError(failure_message)
    return completed.stdout


def _read_regular_file(path: Path, label: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise R2CutoverPreflightError(f"required {label} is missing or unreadable") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise R2CutoverPreflightError(f"required {label} must be a regular file")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            contents = source.read()
    except OSError as error:
        raise R2CutoverPreflightError(f"required {label} is missing or unreadable") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not contents:
        raise R2CutoverPreflightError(f"required {label} must not be empty")
    return contents


def _backup_path(backup_root: Path, release_sha: str, timestamp: datetime) -> Path:
    stamp = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return backup_root / f"{R2_BACKUP_PREFIX}{stamp}-{release_sha[:12]}"


def _write_atomic_backup(
    *, backup_path: Path, config_bytes: bytes, secret_bytes: dict[str, bytes]
) -> None:
    _ensure_backup_root(backup_path.parent)
    if backup_path.exists() or backup_path.is_symlink():
        raise R2CutoverPreflightError("timestamped R2 cutover backup path already exists")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{backup_path.name}.", suffix=".tmp", dir=backup_path.parent)
    )
    try:
        staging.chmod(0o700)
        _write_private_file(staging / "config" / "librarian.json", config_bytes)
        for role in R2_BROKER_SECRET_ROLES:
            _write_private_file(
                staging / "config" / "secrets" / BROKER_SECRET_NAMES[role],
                secret_bytes[role],
            )
        staging.replace(backup_path)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _ensure_backup_root(backup_root: Path) -> None:
    if backup_root.is_symlink():
        raise R2CutoverPreflightError("R2 cutover backup root must not be a symlink")
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not backup_root.is_dir() or backup_root.is_symlink():
        raise R2CutoverPreflightError("R2 cutover backup root must be a directory")
    backup_root.chmod(0o700)


def _write_private_file(path: Path, contents: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = -1
            destination.write(contents)
            destination.flush()
            os.fsync(destination.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "config" / "librarian.json",
        help="Ignored user-owned Librarian configuration to validate and back up.",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=REPO_ROOT / "backups" / "r2-cutover",
        help="Owner-only local directory for timestamped configuration snapshots.",
    )
    args = parser.parse_args()
    try:
        backup = prepare_r2_cutover(
            repository_root=REPO_ROOT,
            config_path=args.config,
            backup_root=args.backup_root,
        )
    except R2CutoverPreflightError as error:
        parser.error(str(error))
    print(f"[librarian] R2 cutover preflight passed for release {backup.release_sha}.")
    print(f"[librarian] Local configuration backup created at {backup.path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
