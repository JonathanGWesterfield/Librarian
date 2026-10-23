"""Tests for the non-disruptive R2 cutover preparation command."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.compose_security import BROKER_SECRET_NAMES

PREFLIGHT_PATH = REPO_ROOT / "scripts" / "prepare_r2_cutover.py"


class R2CutoverPreflightTests(unittest.TestCase):
    def test_valid_inputs_create_one_private_timestamped_backup_after_validation(self) -> None:
        preflight = _load_preflight()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _copy_fixture_config(root)
            backup_root = root / "backups"
            calls: list[list[str]] = []

            def run(command, **kwargs):
                calls.append(list(command))
                return _completed(command, stdout=_command_stdout(command, root))

            with patch.object(preflight.subprocess, "run", side_effect=run):
                backup = preflight.prepare_r2_cutover(
                    repository_root=root,
                    config_path=config,
                    backup_root=backup_root,
                    now=lambda: datetime(
                        2026, 10, 23, 15, 4, 5, tzinfo=timezone.utc
                    ),
                )

            self.assertEqual(backup.release_sha, "a" * 40)
            self.assertEqual(
                backup.path.name,
                "r2-cutover-20261023T150405Z-aaaaaaaaaaaa",
            )
            self.assertEqual(
                (backup.path / "config" / "librarian.json").read_bytes(),
                config.read_bytes(),
            )
            for role, secret_name in BROKER_SECRET_NAMES.items():
                with self.subTest(role=role):
                    self.assertEqual(
                        (backup.path / "config" / "secrets" / secret_name).read_bytes(),
                        (config.parent / "secrets" / secret_name).read_bytes(),
            )
            self.assertEqual((backup.path.stat().st_mode & 0o777), 0o700)
            self.assertTrue(
                all(
                    (path.stat().st_mode & 0o777) == 0o600
                    for path in backup.path.rglob("*")
                    if path.is_file()
                )
            )
            self.assertEqual(
                [command for command in calls if command[:2] == ["docker", "compose"]],
                [_expected_compose_render_command()],
            )

    def test_missing_role_secret_fails_before_compose_or_backup_creation(self) -> None:
        preflight = _load_preflight()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _copy_fixture_config(root)
            (config.parent / "secrets" / "codex-broker-evaluator").unlink()
            backup_root = root / "backups"

            with patch.object(
                preflight.subprocess, "run", side_effect=_git_only_run(root)
            ) as run:
                with self.assertRaisesRegex(
                    preflight.R2CutoverPreflightError, "configuration or credential"
                ):
                    preflight.prepare_r2_cutover(
                        repository_root=root,
                        config_path=config,
                        backup_root=backup_root,
                    )

            self.assertFalse(backup_root.exists())
            self.assertEqual(run.call_count, 3)

    def test_dirty_release_fails_without_reading_config_or_creating_backup(self) -> None:
        preflight = _load_preflight()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _copy_fixture_config(root)
            backup_root = root / "backups"

            def dirty_run(command, **kwargs):
                if command[-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]:
                    return _completed(command, stdout=" M tracked.py\n")
                return _completed(command, stdout=_command_stdout(command, root))

            with patch.object(preflight.subprocess, "run", side_effect=dirty_run):
                with self.assertRaisesRegex(preflight.R2CutoverPreflightError, "clean Git"):
                    preflight.prepare_r2_cutover(
                        repository_root=root,
                        config_path=config,
                        backup_root=backup_root,
                    )

            self.assertFalse(backup_root.exists())

    def test_invalid_rendered_topology_leaves_no_partial_backup(self) -> None:
        preflight = _load_preflight()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _copy_fixture_config(root)
            backup_root = root / "backups"
            invalid = _r2_compose()
            invalid["services"]["codex-broker"]["ports"] = ["50051:50051"]
            original_config_tree = _snapshot_file_tree(config.parent)

            def run(command, **kwargs):
                output = (
                    json.dumps(invalid)
                    if command[:2] == ["docker", "compose"]
                    else _command_stdout(command, root)
                )
                return _completed(command, stdout=output)

            with patch.object(preflight.subprocess, "run", side_effect=run), patch.object(
                preflight,
                "_write_atomic_backup",
                side_effect=AssertionError("backup must not start before topology validation"),
            ) as write_backup:
                with self.assertRaisesRegex(
                    preflight.R2CutoverPreflightError, "topology violates"
                ):
                    preflight.prepare_r2_cutover(
                        repository_root=root,
                        config_path=config,
                        backup_root=backup_root,
                    )

            write_backup.assert_not_called()
            self.assertFalse(backup_root.exists())
            self.assertEqual(_snapshot_file_tree(config.parent), original_config_tree)

    def test_symlinked_role_secret_fails_before_compose_or_backup_creation(self) -> None:
        preflight = _load_preflight()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _copy_fixture_config(root)
            secret = config.parent / "secrets" / "codex-broker-health"
            replacement = root / "replacement-secret"
            replacement.write_text("synthetic-replacement\n", encoding="utf-8")
            secret.unlink()
            os.symlink(replacement, secret)
            backup_root = root / "backups"

            with patch.object(
                preflight.subprocess, "run", side_effect=_git_only_run(root)
            ):
                with self.assertRaisesRegex(
                    preflight.R2CutoverPreflightError, "configuration or credential"
                ):
                    preflight.prepare_r2_cutover(
                        repository_root=root,
                        config_path=config,
                        backup_root=backup_root,
                    )

            self.assertFalse(backup_root.exists())


def _load_preflight():
    spec = importlib.util.spec_from_file_location(
        f"r2_cutover_preflight_{id(PREFLIGHT_PATH)}", PREFLIGHT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_fixture_config(root: Path) -> Path:
    source = (
        REPO_ROOT / "tests" / "fixtures" / "answer_delivery" / "r2-compose" / "config"
    )
    target = root / "config"
    shutil.copytree(source, target)
    return target / "librarian.json"


def _snapshot_file_tree(root: Path) -> dict[Path, bytes]:
    """Return every source config/secret path and its bytes for mutation checks."""

    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _git_only_run(root: Path):
    def run(command, **kwargs):
        if command[:2] == ["docker", "compose"]:
            self_fail = AssertionError("Compose rendering must not run after invalid credentials")
            raise self_fail
        return _completed(command, stdout=_command_stdout(command, root))

    return run


def _command_stdout(command, root: Path) -> str:
    if command[-1:] == ["--show-toplevel"]:
        return f"{root}\n"
    if command[-1:] == ["HEAD"]:
        return "a" * 40 + "\n"
    if command[:2] == ["docker", "compose"]:
        return json.dumps(_r2_compose())
    return ""


def _expected_compose_render_command() -> list[str]:
    return [
        "docker",
        "compose",
        "--profile",
        "codex-broker",
        "--profile",
        "workers",
        "--profile",
        "metadata-workers",
        "--profile",
        "evaluation",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.r2.yml",
        "config",
        "--format",
        "json",
    ]


def _completed(command, *, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


def _r2_compose() -> dict[str, object]:
    roles = ("api", "summary-worker", "metadata-worker", "evaluator")
    private_networks = {
        "api": "broker-api",
        "summary-worker": "broker-summary-worker",
        "metadata-worker": "broker-metadata-worker",
        "evaluator": "broker-evaluator",
    }
    compose: dict[str, object] = {
        "networks": {
            "application": {},
            "broker-api": {"internal": True},
            "broker-summary-worker": {"internal": True},
            "broker-metadata-worker": {"internal": True},
            "broker-evaluator": {"internal": True},
            "broker-egress": {},
        },
        "secrets": {
            secret: {"file": f"./config/secrets/{secret}"}
            for secret in BROKER_SECRET_NAMES.values()
        },
        "services": {
            "codex-broker": {
                "networks": [*private_networks.values(), "broker-egress"],
                "expose": ["50051"],
                "secrets": [_secret_mount(role) for role in (*roles, "compose-health")],
                "volumes": [
                    "./.runtime/config/codex-broker/librarian.json:/config/librarian.json:ro"
                ],
            },
            "web": {"networks": ["application"], "volumes": []},
        },
    }
    services = compose["services"]
    assert isinstance(services, dict)
    for role in roles:
        services[role] = {
            "networks": ["application", private_networks[role]],
            "secrets": [_secret_mount(role)],
                "volumes": [
                    f"./.runtime/config/{role}/librarian.json:/config/librarian.json:ro"
                ],
            "environment": {
                "LIBRARIAN_EXECUTION_PRINCIPAL": role,
                "LIBRARIAN_BROKER_CREDENTIAL_FILE": f"/run/secrets/{BROKER_SECRET_NAMES[role]}",
            },
        }
    return copy.deepcopy(compose)


def _secret_mount(role: str) -> dict[str, object]:
    secret = BROKER_SECRET_NAMES[role]
    return {"source": secret, "target": secret, "mode": "0400"}


if __name__ == "__main__":
    unittest.main()
