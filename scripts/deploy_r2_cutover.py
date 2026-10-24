"""Atomically activate the R2 Compose stack from a prepared local backup.

The default command is a non-destructive plan.  Activation requires the exact
``--confirm-r2-cutover`` acknowledgement because it stops the current R0 web
admission path, replaces the Compose stack, and may restore it on failure.

Example:
    python3 scripts/deploy_r2_cutover.py --backup backups/r2-cutover/<snapshot>
    python3 scripts/deploy_r2_cutover.py --backup backups/r2-cutover/<snapshot> \
        --confirm-r2-cutover

The command never copies a secret to stdout, a report, or a command argument.
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
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(SCRIPT_DIRECTORY))

from librarian_config.config import LibrarianConfigError, get_librarian_config
from librarian_config.write_lease import (
    ConfigurationWriteLease,
    ConfigurationWriteLeaseError,
    acquire_configuration_write_lease,
)

from prepare_r2_cutover import (
    BROKER_SECRET_NAMES,
    R2_BROKER_SECRET_ROLES,
    R2CutoverBackup,
    R2CutoverPreflightError,
    R2_BACKUP_MANIFEST_NAME,
    _read_regular_file,
    _require_clean_release,
)

R2_PROFILES = ("codex-broker", "workers", "metadata-workers", "evaluation")
R2_SERVICES = (
    "opensearch",
    "ollama",
    "api",
    "web",
    "codex-broker",
    "summary-worker",
    "metadata-worker",
)
R0_RESTORE_SERVICES = ("opensearch", "ollama", "api", "web", "codex-broker", "summary-worker")
DEPLOYMENT_RECORD_NAME = "deployment.json"
R0_IMAGES_RECORD_NAME = "r0-images.json"


class R2CutoverDeploymentError(RuntimeError):
    """The R2 cutover did not reach a safe, confirmed terminal state."""


@dataclass(frozen=True)
class R0Image:
    """One locally available image needed to reconstruct the R0 baseline."""

    repository: str
    tag: str
    image_id: str

    @property
    def reference(self) -> str:
        return f"{self.repository}:{self.tag}"


@dataclass(frozen=True)
class R2CutoverDeployment:
    """A redacted record of a planned, active, or rolled-back cutover."""

    release_sha: str
    backup_path: Path
    correlation_id: str
    state: str
    already_active: bool = False
    planned_commands: tuple[tuple[str, ...], ...] = ()


@dataclass
class R2InputLock:
    """The durable config-writer lease and modes for rollback staging."""

    lease: ConfigurationWriteLease
    config_directory_mode: int
    secrets_directory_mode: int
    file_modes: tuple[tuple[Path, int], ...]


CommandRunner = Callable[[Sequence[str], Path, Mapping[str, str]], subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]


def deploy_r2_cutover(
    *,
    repository_root: Path,
    backup: R2CutoverBackup,
    confirm: bool,
    drain_seconds: float = 30.0,
    runner: CommandRunner | None = None,
    sleeper: Sleeper = time.sleep,
    correlation_id: str | None = None,
) -> R2CutoverDeployment:
    """Plan or activate R2, restoring the complete R0 baseline on failure.

    A successful preflight snapshot is a mandatory input.  Before any service
    changes the command verifies its release binding, validates the snapshot,
    captures the exact locally running R0 images, and runs the tracked
    deterministic checks.  It then closes browser admission, drains R0,
    recreates every R2 service in one Compose action, and proves every caller's
    capability startup.  Any failure after R0 admission closes restores the
    saved images and snapshot before returning an error.
    """

    if drain_seconds < 0:
        raise R2CutoverDeploymentError("R2 drain duration must not be negative")
    root = repository_root.resolve()
    release_sha = _validate_backup(root, backup)
    _validate_live_inputs_match_backup(root / "config", backup.path / "config")
    record = _load_record(backup.path)
    if record is not None:
        _validate_record(record, backup, release_sha)
        if record["state"] == "r2_active":
            return R2CutoverDeployment(
                release_sha=release_sha,
                backup_path=backup.path,
                correlation_id=record["correlation_id"],
                state="r2_active",
                already_active=True,
            )
        raise R2CutoverDeploymentError(
            "cutover backup has an incomplete or rolled-back deployment record; "
            "prepare a new R2 backup before retrying"
        )

    correlation = correlation_id or str(uuid.uuid4())
    if not _is_correlation_id(correlation):
        raise R2CutoverDeploymentError("R2 cutover correlation ID must be a canonical UUID")
    if not confirm:
        return R2CutoverDeployment(
            release_sha=release_sha,
            backup_path=backup.path,
            correlation_id=correlation,
            state="planned",
            planned_commands=_planned_commands(root, correlation),
        )

    run = runner or _run_command
    environment = {
        **os.environ,
        "LIBRARIAN_STACK_RELEASE_SHA": release_sha,
        "LIBRARIAN_CUTOVER_ID": correlation,
    }
    r0_compose = _compose_command(root, profiles=(), include_runtime=False)
    r2_compose = _compose_command(root, profiles=R2_PROFILES, include_runtime=False)
    r2_runtime_compose = _compose_command(root, profiles=R2_PROFILES, include_runtime=True)

    images = _capture_r0_images(run, r0_compose, root, environment)
    _write_images_record(backup.path, release_sha, correlation, images)
    _write_record(backup.path, release_sha, correlation, "validated")
    # These gates can build isolated acceptance images but must never stop or
    # recreate the operator's R0 services. A failure here leaves R0 intact.
    _run_release_gates(run, root, environment, correlation)
    _validate_live_inputs_match_backup(root / "config", backup.path / "config")
    _run_checked(run, [*r2_compose, "build", *R2_SERVICES, "evaluator"], root, environment)
    _run_checked(
        run,
        [*r2_compose, "run", "--rm", "config-resolver"],
        root,
        environment,
    )
    _validate_live_inputs_match_backup(root / "config", backup.path / "config")
    input_lock = _lock_r2_inputs(root / "config", backup.path / "config")

    # From this point an R0 service may have been stopped. Every failure must
    # therefore restore the saved image/configuration set before returning.
    _write_record(backup.path, release_sha, correlation, "r0_admission_closed")
    try:
        _run_checked(run, [*r0_compose, "stop", "web"], root, environment)
        if drain_seconds:
            sleeper(drain_seconds)
        _run_checked(run, [*r0_compose, "down", "--remove-orphans"], root, environment)
        _write_record(backup.path, release_sha, correlation, "r2_activating")
        _run_checked(
            run,
            [
                *r2_runtime_compose,
                "up",
                "--build",
                "--detach",
                "--wait",
                "--force-recreate",
                "--remove-orphans",
                *R2_SERVICES,
            ],
            root,
            environment,
        )
        _run_r2_readiness_checks(run, r2_runtime_compose, root, environment)
        _run_deterministic_r2_smoke(run, root, environment, correlation, stage="post-readiness")
    except BaseException as original_error:
        try:
            _rollback_r0(
                run=run,
                root=root,
                environment=environment,
                r0_compose=r0_compose,
                r2_compose=r2_runtime_compose,
                backup_path=backup.path,
                images=images,
                input_lock=input_lock,
            )
        except BaseException as rollback_error:
            _write_record(backup.path, release_sha, correlation, "rollback_failed")
            raise R2CutoverDeploymentError(
                "R2 activation failed and automatic R0 rollback also failed; "
                "do not start either stack manually before inspecting the local backup"
            ) from rollback_error
        _write_record(backup.path, release_sha, correlation, "rolled_back")
        raise R2CutoverDeploymentError("R2 activation failed; the complete R0 baseline was restored") from original_error
    finally:
        _unlock_r2_inputs(root / "config", input_lock)

    _write_record(backup.path, release_sha, correlation, "r2_active")
    return R2CutoverDeployment(
        release_sha=release_sha,
        backup_path=backup.path,
        correlation_id=correlation,
        state="r2_active",
    )


def _validate_backup(repository_root: Path, backup: R2CutoverBackup) -> str:
    try:
        release_sha = _require_clean_release(repository_root)
    except R2CutoverPreflightError as error:
        raise R2CutoverDeploymentError("R2 deployment requires the original clean release") from error
    if backup.release_sha != release_sha:
        raise R2CutoverDeploymentError("R2 backup release SHA does not match the current release")
    backup_path = backup.path.absolute()
    if not backup_path.is_dir() or backup_path.is_symlink():
        raise R2CutoverDeploymentError("R2 cutover backup directory is unavailable")
    expected = {Path("config/librarian.json")}
    expected.update(
        Path("config/secrets") / BROKER_SECRET_NAMES[role] for role in R2_BROKER_SECRET_ROLES
    )
    actual = {
        path.relative_to(backup_path)
        for path in backup_path.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    allowed = expected | {
        Path(R2_BACKUP_MANIFEST_NAME),
        Path(DEPLOYMENT_RECORD_NAME),
        Path(R0_IMAGES_RECORD_NAME),
    }
    if actual - allowed or not expected.issubset(actual):
        raise R2CutoverDeploymentError("R2 cutover backup contents are incomplete or unexpected")
    if _backup_release_sha(backup_path) != backup.release_sha:
        raise R2CutoverDeploymentError("R2 cutover backup manifest does not match its release")
    config_path = backup_path / "config" / "librarian.json"
    try:
        _read_regular_file(config_path, "cutover backup configuration")
        config = get_librarian_config(config_path)
        if not config.uses_docker_codex_broker:
            raise LibrarianConfigError("R2 backup does not select the Codex broker")
        for role in R2_BROKER_SECRET_ROLES:
            _read_regular_file(
                backup_path / "config" / "secrets" / BROKER_SECRET_NAMES[role],
                "cutover backup credential",
            )
    except (R2CutoverPreflightError, LibrarianConfigError) as error:
        raise R2CutoverDeploymentError("R2 cutover backup inputs are invalid") from error
    return release_sha



def _validate_live_inputs_match_backup(destination_root: Path, source_root: Path) -> None:
    """Refuse cutover when user-owned inputs changed after preflight.

    The snapshot is only safe to restore after a failed activation when it is
    still the exact configuration and credential set that preflight validated.
    This check runs before image builds or admission changes, and is repeated
    immediately before rollback writes to close the normal operator-change
    window without ever disclosing credential material.
    """

    for relative_path in _r0_input_paths():
        try:
            current = _read_regular_file(destination_root / relative_path, "local cutover input")
            saved = _read_regular_file(source_root / relative_path, "cutover backup input")
        except R2CutoverPreflightError as error:
            raise R2CutoverDeploymentError(
                "local R2 configuration or credentials changed after preflight"
            ) from error
        if current != saved:
            raise R2CutoverDeploymentError(
                "local R2 configuration or credentials changed after preflight"
            )


def _r0_input_paths() -> tuple[Path, ...]:
    return (
        Path("librarian.json"),
        *(Path("secrets") / BROKER_SECRET_NAMES[role] for role in R2_BROKER_SECRET_ROLES),
    )

def _lock_r2_inputs(destination_root: Path, source_root: Path) -> R2InputLock:
    """Hold the shared writer lease through activation and possible rollback.

    File permissions cannot protect a same-owner configuration edit.  Instead,
    the durable repository-level lease is acquired before the final input
    validation.  Every Librarian command that writes live ``config/`` uses the
    same non-blocking lease, so it cannot begin a write between validation and
    the rollback directory publish.
    """

    try:
        lease = acquire_configuration_write_lease(destination_root.parent)
    except ConfigurationWriteLeaseError as error:
        raise R2CutoverDeploymentError(
            "could not acquire the exclusive R2 configuration write lease"
        ) from error
    secrets_directory = destination_root / "secrets"
    try:
        # A writer may have completed immediately before the lease was
        # acquired. Validate only after acquisition, then retain the same lock
        # until the activation either succeeds or R0 has been restored.
        _validate_live_inputs_match_backup(destination_root, source_root)
        if destination_root.is_symlink() or secrets_directory.is_symlink():
            raise R2CutoverDeploymentError("local R2 configuration directory is unavailable")
        config_mode = stat.S_IMODE(destination_root.stat().st_mode)
        secrets_mode = stat.S_IMODE(secrets_directory.stat().st_mode)
        file_modes = tuple(
            (relative_path, stat.S_IMODE((destination_root / relative_path).stat().st_mode))
            for relative_path in _r0_input_paths()
        )
    except BaseException:
        lease.release()
        raise
    return R2InputLock(lease, config_mode, secrets_mode, file_modes)


def _unlock_r2_inputs(destination_root: Path, lock: R2InputLock | None) -> None:
    """Release the durable writer lease without changing live input bytes."""

    del destination_root
    if lock is not None:
        lock.lease.release()


def _compose_command(
    root: Path, *, profiles: Sequence[str], include_runtime: bool) -> list[str]:
    command = ["docker", "compose"]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("-f", "docker-compose.yml"))
    if profiles:
        command.extend(("-f", "docker-compose.r2.yml"))
    if include_runtime:
        command.extend(("-f", ".runtime/librarian.compose.json"))
    return command



def _planned_commands(root: Path, correlation_id: str) -> tuple[tuple[str, ...], ...]:
    """Return the redacted lifecycle commands without operating Compose."""

    r0_compose = _compose_command(root, profiles=(), include_runtime=False)
    r2_compose = _compose_command(root, profiles=R2_PROFILES, include_runtime=False)
    r2_runtime_compose = _compose_command(root, profiles=R2_PROFILES, include_runtime=True)
    return (
        tuple([*r0_compose, "images", "--format", "json"]),
        ("scripts/run_answer_delivery_contract_gate.sh",),
        ("scripts/run_answer_delivery_compose.sh",),
        tuple([*r2_compose, "build", *R2_SERVICES, "evaluator"]),
        tuple([*r2_compose, "run", "--rm", "config-resolver"]),
        tuple([*r0_compose, "stop", "web"]),
        tuple([*r0_compose, "down", "--remove-orphans"]),
        tuple(
            [
                *r2_runtime_compose,
                "up",
                "--build",
                "--detach",
                "--wait",
                "--force-recreate",
                "--remove-orphans",
                *R2_SERVICES,
            ]
        ),
        tuple([*r2_runtime_compose, "exec", "-T", "api", "<R2 API health probe>"]),
        tuple([*r2_runtime_compose, "run", "--rm", "--no-deps", "evaluator", "<R2 evaluator handshake>"]),
    )

def _run_release_gates(
    run: CommandRunner,
    root: Path,
    environment: Mapping[str, str],
    correlation_id: str,
) -> None:
    _run_checked(
        run,
        ["scripts/run_answer_delivery_contract_gate.sh"],
        root,
        environment,
    )
    _run_deterministic_r2_smoke(run, root, environment, correlation_id, stage="pre-cutover")


def _run_deterministic_r2_smoke(
    run: CommandRunner,
    root: Path,
    environment: Mapping[str, str],
    correlation_id: str,
    *,
    stage: str,
) -> None:
    """Run the tracked fake-provider operation matrix without local credentials.

    The harness exercises chat, summary, tag, genre, recommendation, and
    evaluator operations for every permitted role against a disposable project.
    It is intentionally run once before service disruption and once after the
    real R2 callers pass readiness, before browser admission is restored.
    """

    report_dir = Path(tempfile.gettempdir()) / f"librarian-r2-cutover-{correlation_id}-{stage}"
    _run_checked(
        run,
        ["scripts/run_answer_delivery_compose.sh"],
        root,
        {
            **environment,
            "VERIFY_PROJECT": f"librarian-r2-{correlation_id[:8]}-{stage}",
            "ANSWER_DELIVERY_REPORT_DIR": str(report_dir),
        },
    )


def _capture_r0_images(
    run: CommandRunner,
    compose: Sequence[str],
    root: Path,
    environment: Mapping[str, str],
) -> tuple[R0Image, ...]:
    completed = _run_checked(run, [*compose, "images", "--format", "json"], root, environment)
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as error:
        raise R2CutoverDeploymentError("could not record the R0 image baseline") from error
    if not isinstance(payload, list):
        raise R2CutoverDeploymentError("could not record the R0 image baseline")
    images: list[R0Image] = []
    for value in payload:
        if not isinstance(value, dict):
            raise R2CutoverDeploymentError("could not record the R0 image baseline")
        repository = value.get("Repository")
        tag = value.get("Tag")
        image_id = value.get("ID", value.get("ImageID"))
        if not all(isinstance(item, str) and item for item in (repository, tag, image_id)):
            raise R2CutoverDeploymentError("could not record the R0 image baseline")
        images.append(R0Image(repository=repository, tag=tag, image_id=image_id))
    if not images:
        raise R2CutoverDeploymentError("R2 cutover requires a running R0 image baseline")
    return tuple(sorted(set(images), key=lambda image: image.reference))


def _run_r2_readiness_checks(
    run: CommandRunner,
    compose: Sequence[str],
    root: Path,
    environment: Mapping[str, str],
) -> None:
    _run_checked(
        run,
        [*compose, "exec", "-T", "api", "python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=5).read()"],
        root,
        environment,
    )
    _run_checked(
        run,
        [
            *compose,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "python",
            "evaluator",
            "-m",
            "librarian_answer_adapters.r2_startup",
            "--principal",
            "evaluator",
            "--",
            "python",
            "-c",
            "pass",
        ],
        root,
        environment,
    )


def _rollback_r0(
    *,
    run: CommandRunner,
    root: Path,
    environment: Mapping[str, str],
    r0_compose: Sequence[str],
    r2_compose: Sequence[str],
    backup_path: Path,
    images: Sequence[R0Image],
    input_lock: R2InputLock,
) -> None:
    _run_checked(run, [*r2_compose, "down", "--remove-orphans"], root, environment)
    _restore_r0_inputs(root / "config", backup_path / "config", input_lock)
    for image in images:
        _run_checked(run, ["docker", "image", "tag", image.image_id, image.reference], root, environment)
    _run_checked(
        run,
        [
            *r0_compose,
            "up",
            "--detach",
            "--wait",
            "--no-build",
            "--force-recreate",
            "--remove-orphans",
            *R0_RESTORE_SERVICES,
        ],
        root,
        environment,
    )


def _restore_r0_inputs(
    destination_root: Path, source_root: Path, input_lock: R2InputLock
) -> None:
    """Restore the exact preflight inputs with one configuration-directory swap.

    R0 is down before this runs.  We first prove that the user-owned inputs are
    still byte-for-byte the preflight set, then stage a full copy of ``config``
    that preserves unrelated files such as the legacy bridge token.  Renaming
    the staged directory publishes all five R2 role credentials and the R2
    configuration together; if the publish rename fails, the original
    directory is immediately put back.  No secret bytes enter error messages.
    """

    _validate_live_inputs_match_backup(destination_root, source_root)
    if destination_root.is_symlink() or not destination_root.is_dir():
        raise R2CutoverDeploymentError("local R2 configuration directory is unavailable")
    parent = destination_root.parent
    staging = Path(tempfile.mkdtemp(prefix=".r2-restore.", dir=parent))
    original = parent / f".{destination_root.name}.r2-rollback-{uuid.uuid4().hex}"
    moved_original = False
    try:
        shutil.rmtree(staging)
        shutil.copytree(destination_root, staging, symlinks=True)
        # The shared writer lease protects the live inputs. The private
        # staging copy regains writable owner modes so replacement files can
        # be prepared without changing the live configuration.
        os.chmod(staging, input_lock.config_directory_mode)
        os.chmod(staging / "secrets", input_lock.secrets_directory_mode)
        for relative_path, mode in input_lock.file_modes:
            os.chmod(staging / relative_path, mode | stat.S_IWUSR)
        for relative_path in _r0_input_paths():
            _write_private_file(
                staging / relative_path,
                _read_regular_file(source_root / relative_path, "cutover backup input"),
            )
        # The shared writer lease remains held. Verify immediately before
        # the only destructive rename to reject any non-cooperating edit that
        # completed before this final check. Cooperating writers cannot enter
        # the validation-to-publish interval at all.
        _validate_live_inputs_match_backup(destination_root, source_root)
        destination_root.replace(original)
        moved_original = True
        try:
            staging.replace(destination_root)
        except BaseException:
            original.replace(destination_root)
            moved_original = False
            raise
        _remove_replaced_config(original)
        moved_original = False
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if moved_original and original.exists() and not destination_root.exists():
            original.replace(destination_root)


def _remove_replaced_config(path: Path) -> None:
    """Best-effort cleanup of the locked directory after it is no longer live."""

    try:
        for directory, directories, files in os.walk(path, topdown=False, followlinks=False):
            directory_path = Path(directory)
            for name in (*directories, *files):
                child = directory_path / name
                if not child.is_symlink():
                    os.chmod(child, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            os.chmod(directory_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        shutil.rmtree(path)
    except OSError:
        # R0 has already been restored from the new active directory. Leave a
        # private, owner-readable old snapshot rather than weaken its modes or
        # turn a cleanup issue into a mixed-stack recovery failure.
        pass


def _write_private_file(path: Path, contents: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _run_checked(
    run: CommandRunner,
    command: Sequence[str],
    root: Path,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    completed = run(command, root, environment)
    if completed.returncode != 0:
        raise R2CutoverDeploymentError("R2 cutover command failed")
    return completed


def _run_command(
    command: Sequence[str], root: Path, environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, check=False)


def _load_record(backup_path: Path) -> dict[str, str] | None:
    path = backup_path / DEPLOYMENT_RECORD_NAME
    if not path.exists():
        return None
    try:
        raw = _read_regular_file(path, "deployment record")
        payload = json.loads(raw)
    except (R2CutoverPreflightError, json.JSONDecodeError) as error:
        raise R2CutoverDeploymentError("R2 cutover deployment record is invalid") from error
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "release_sha", "correlation_id", "state"}:
        raise R2CutoverDeploymentError("R2 cutover deployment record is invalid")
    if payload.get("schema_version") != 1 or not all(isinstance(payload[key], str) for key in ("release_sha", "correlation_id", "state")):
        raise R2CutoverDeploymentError("R2 cutover deployment record is invalid")
    return payload


def _validate_record(record: Mapping[str, str], backup: R2CutoverBackup, release_sha: str) -> None:
    if record["release_sha"] != release_sha or record["release_sha"] != backup.release_sha:
        raise R2CutoverDeploymentError("R2 cutover deployment record does not match its release")
    if not _is_correlation_id(record["correlation_id"]):
        raise R2CutoverDeploymentError("R2 cutover deployment record has an invalid correlation ID")
    if record["state"] not in {"validated", "r0_admission_closed", "r2_activating", "r2_active", "rolled_back", "rollback_failed"}:
        raise R2CutoverDeploymentError("R2 cutover deployment record has an invalid state")


def _write_record(backup_path: Path, release_sha: str, correlation_id: str, state: str) -> None:
    _write_private_json(
        backup_path / DEPLOYMENT_RECORD_NAME,
        {
            "schema_version": 1,
            "release_sha": release_sha,
            "correlation_id": correlation_id,
            "state": state,
        },
    )


def _write_images_record(
    backup_path: Path, release_sha: str, correlation_id: str, images: Sequence[R0Image]
) -> None:
    path = backup_path / R0_IMAGES_RECORD_NAME
    payload = {
        "schema_version": 1,
        "release_sha": release_sha,
        "correlation_id": correlation_id,
        "images": [asdict(image) for image in images],
    }
    if path.exists():
        try:
            existing = json.loads(_read_regular_file(path, "R0 image record"))
        except (R2CutoverPreflightError, json.JSONDecodeError) as error:
            raise R2CutoverDeploymentError("R0 image record is invalid") from error
        if existing != payload:
            raise R2CutoverDeploymentError("R0 image record does not match this cutover")
        return
    _write_private_json(path, payload)


def _write_private_json(path: Path, payload: Mapping[str, object]) -> None:
    data = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _is_correlation_id(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True, help="Prepared R2 cutover backup directory.")
    parser.add_argument(
        "--confirm-r2-cutover",
        action="store_true",
        help="Acknowledge that this command will replace R0 and may restore it on failure.",
    )
    parser.add_argument(
        "--drain-seconds",
        type=float,
        default=30.0,
        help="Seconds to allow existing R0 API work after browser admission closes.",
    )
    args = parser.parse_args(argv)
    try:
        deployment = deploy_r2_cutover(
            repository_root=REPO_ROOT,
            backup=R2CutoverBackup(release_sha=_backup_release_sha(args.backup), path=args.backup),
            confirm=args.confirm_r2_cutover,
            drain_seconds=args.drain_seconds,
        )
    except R2CutoverDeploymentError as error:
        parser.error(str(error))
    if deployment.state == "planned":
        print("[librarian] R2 cutover plan is valid. Re-run with --confirm-r2-cutover to activate it.")
        for command in deployment.planned_commands:
            print("[librarian] planned: " + " ".join(command))
    elif deployment.already_active:
        print("[librarian] This R2 cutover is already active; no Compose command was repeated.")
    else:
        print("[librarian] R2 cutover is active.")
    print(f"[librarian] release={deployment.release_sha} correlation_id={deployment.correlation_id}")
    return 0


def _backup_release_sha(backup_path: Path) -> str:
    """Read the immutable release binding written by preflight."""

    try:
        raw = _read_regular_file(backup_path / R2_BACKUP_MANIFEST_NAME, "cutover backup manifest")
        payload = json.loads(raw)
    except (R2CutoverPreflightError, json.JSONDecodeError) as error:
        raise R2CutoverDeploymentError("R2 cutover backup manifest is invalid") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "release_sha"}
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("release_sha"), str)
    ):
        raise R2CutoverDeploymentError("R2 cutover backup manifest is invalid")
    release_sha = payload["release_sha"]
    if len(release_sha) != 40 or any(character not in "0123456789abcdef" for character in release_sha):
        raise R2CutoverDeploymentError("R2 cutover backup manifest is invalid")
    return release_sha


if __name__ == "__main__":
    raise SystemExit(main())
