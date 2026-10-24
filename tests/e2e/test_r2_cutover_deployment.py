"""Sandboxed lifecycle coverage for the R2 activation and R0 rollback command."""

from __future__ import annotations

import importlib.util
import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_PATH = REPO_ROOT / "scripts" / "deploy_r2_cutover.py"
FIXTURE_CONFIG = REPO_ROOT / "tests" / "fixtures" / "answer_delivery" / "r2-compose" / "config"
RELEASE_SHA = "a" * 40
CORRELATION_ID = "00000000-0000-4000-8000-000000000000"


class R2CutoverDeploymentTests(unittest.TestCase):
    def test_plan_is_non_destructive_and_lists_the_atomic_lifecycle(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner()
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                result = deployment.deploy_r2_cutover(
                    repository_root=root,
                    backup=backup,
                    confirm=False,
                    runner=runner,
                    correlation_id=CORRELATION_ID,
                )

        self.assertEqual(result.state, "planned")
        self.assertFalse(result.already_active)
        self.assertEqual(runner.calls, [])
        self.assertIn(("docker", "compose", "-f", "docker-compose.yml", "stop", "web"), result.planned_commands)
        self.assertTrue(
            any("--force-recreate" in command and "--wait" in command for command in result.planned_commands)
        )

    def test_successful_activation_records_correlation_and_preserves_command_order(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner()
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                result = deployment.deploy_r2_cutover(
                    repository_root=root,
                    backup=backup,
                    confirm=True,
                    drain_seconds=0,
                    runner=runner,
                    sleeper=lambda seconds: self.fail("zero drain must not sleep"),
                    correlation_id=CORRELATION_ID,
                )

            record = json.loads((backup.path / deployment.DEPLOYMENT_RECORD_NAME).read_text())
            images = json.loads((backup.path / deployment.R0_IMAGES_RECORD_NAME).read_text())

        self.assertEqual(result.state, "r2_active")
        self.assertEqual(record["state"], "r2_active")
        self.assertEqual(record["correlation_id"], CORRELATION_ID)
        self.assertEqual(images["release_sha"], RELEASE_SHA)
        calls = [call.command for call in runner.calls]
        self.assertLess(_index(calls, ("images", "--format", "json")), _index(calls, ("scripts/run_answer_delivery_contract_gate.sh",)))
        self.assertLess(_index(calls, ("scripts/run_answer_delivery_compose.sh",)), _index(calls, ("build",)))
        smoke_indexes = [
            index
            for index, command in enumerate(calls)
            if command == ("scripts/run_answer_delivery_compose.sh",)
        ]
        self.assertEqual(len(smoke_indexes), 2)
        self.assertLess(_index(calls, ("exec", "-T", "api")), smoke_indexes[1])
        self.assertLess(_index(calls, ("stop", "web")), _index(calls, ("down", "--remove-orphans")))
        self.assertLess(_index(calls, ("down", "--remove-orphans")), _index(calls, ("up", "--build")))
        self.assertLess(_index(calls, ("up", "--build")), _index(calls, ("exec", "-T", "api")))
        build = next(command for command in calls if _contains(command, ("build",)))
        activation = next(command for command in calls if _contains(command, ("up", "--build")))
        self.assertIn("evaluator", build)
        self.assertNotIn("evaluator", activation)
        self.assertTrue(all(call.environment["LIBRARIAN_CUTOVER_ID"] == CORRELATION_ID for call in runner.calls))
        self.assertTrue(all("synthetic-token" not in " ".join(call.command) for call in runner.calls))

    def test_invalid_backup_or_release_never_operates_compose(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner()
            with patch.object(deployment, "_require_clean_release", return_value="b" * 40):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "does not match"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )

        self.assertEqual(runner.calls, [])

    def test_backup_without_its_release_manifest_never_operates_compose(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            (backup.path / deployment.R2_BACKUP_MANIFEST_NAME).unlink()
            runner = _Runner()
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "manifest"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )

        self.assertEqual(runner.calls, [])

    def test_contract_gate_is_read_only_and_does_not_stage_local_config(self) -> None:
        gate = (REPO_ROOT / "scripts" / "run_answer_delivery_contract_gate.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("git -C \"$root_dir\" archive --format=tar", gate)
        self.assertNotIn("--volume", gate)
        self.assertNotIn("$root_dir:/workspace", gate)
        self.assertIn("--read-only", gate)
        self.assertIn("--workdir /app", gate)
        self.assertIn("PYTHONPATH=/app/packages", gate)
        self.assertIn("test ! -e \"$stage_dir/config/librarian.json\"", gate)
        self.assertIn("test ! -e \"$stage_dir/config/secrets\"", gate)
        self.assertIn("tests.e2e.test_r2_compose_overlay", gate)
        self.assertIn("result.skipped", gate)
        self.assertNotIn("scripts/test.sh", gate)

    def test_release_gate_failure_leaves_r0_running_without_a_rollback(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner(fail_when=("scripts/run_answer_delivery_contract_gate.sh",))
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "command failed"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )

        commands = [call.command for call in runner.calls]
        self.assertFalse(any(_contains(command, ("stop", "web")) for command in commands))
        self.assertFalse(any(_contains(command, ("up", "--detach")) for command in commands))
        self.assertFalse(any(command[:3] == ("docker", "image", "tag") for command in commands))

    def test_r2_readiness_failure_restores_images_config_and_r0_as_one_recovery(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner(fail_when=("exec", "-T", "api"))
            config = root / "config" / "librarian.json"
            legacy_token = root / "config" / "codex-bridge-token.txt"
            legacy_token.write_text("legacy-token-is-unrelated\n", encoding="utf-8")
            before = config.read_bytes()
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "baseline was restored"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        drain_seconds=0,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(legacy_token.read_text(encoding="utf-8"), "legacy-token-is-unrelated\n")
            self.assertEqual(list(root.glob(".config.r2-rollback-*")), [])
            record = json.loads((backup.path / deployment.DEPLOYMENT_RECORD_NAME).read_text())
            self.assertEqual(record["state"], "rolled_back")

        commands = [call.command for call in runner.calls]
        self.assertTrue(any(command[:3] == ("docker", "image", "tag") for command in commands))
        rollback_down = [command for command in commands if command[-2:] == ("down", "--remove-orphans")]
        self.assertGreaterEqual(len(rollback_down), 2)
        self.assertTrue(any("--no-build" in command and "--force-recreate" in command for command in commands))

    def test_rollback_failure_is_reported_and_does_not_claim_r0_is_healthy(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner(fail_when=("exec", "-T", "api"), fail_after=1, fail_rollback=True)
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "rollback also failed"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        drain_seconds=0,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )
            record = json.loads((backup.path / deployment.DEPLOYMENT_RECORD_NAME).read_text())

        self.assertEqual(record["state"], "rollback_failed")


    def test_post_readiness_smoke_failure_rolls_back_r0(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            runner = _Runner(
                fail_when=("scripts/run_answer_delivery_compose.sh",),
                fail_at=2,
            )
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "baseline was restored"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        drain_seconds=0,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )

            record = json.loads((backup.path / deployment.DEPLOYMENT_RECORD_NAME).read_text())

        calls = [call.command for call in runner.calls]
        self.assertEqual(record["state"], "rolled_back")
        self.assertLess(_index(calls, ("exec", "-T", "api")), _index(calls, ("docker", "image", "tag")))
        self.assertTrue(any(command[-2:] == ("down", "--remove-orphans") for command in calls))

    def test_changed_local_inputs_are_never_silently_overwritten_during_rollback(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            config = root / "config" / "librarian.json"

            def change_config() -> None:
                # A process that deliberately changes permissions can bypass
                # the ordinary cutover write lock. The final identity check
                # must preserve this content instead of swapping it away.
                os.chmod(root / "config", 0o700)
                os.chmod(config, 0o600)
                config.write_text("operator-change-after-preflight\n", encoding="utf-8")

            runner = _Runner(
                fail_when=("exec", "-T", "api"),
                before_failure=change_config,
            )
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "rollback also failed"):
                    deployment.deploy_r2_cutover(
                        repository_root=root,
                        backup=backup,
                        confirm=True,
                        drain_seconds=0,
                        runner=runner,
                        correlation_id=CORRELATION_ID,
                    )

            self.assertEqual(config.read_text(encoding="utf-8"), "operator-change-after-preflight\n")
            record = json.loads((backup.path / deployment.DEPLOYMENT_RECORD_NAME).read_text())
            self.assertEqual(record["state"], "rollback_failed")

    def test_cooperating_writer_cannot_enter_after_final_validation_before_publish(self) -> None:
        """The writer lease closes the validation-to-directory-swap window."""

        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            config = root / "config" / "librarian.json"
            original_replace = Path.replace
            attempted: list[bool] = []

            def replace(path: Path, target: Path):
                # This is the precise irreversible publish call, immediately
                # after _restore_r0_inputs performs its final byte check.
                if path.resolve() == config.parent.resolve() and target.name.startswith(".config.r2-rollback-"):
                    attempted.append(True)
                    with self.assertRaises(deployment.ConfigurationWriteLeaseError):
                        with deployment.acquire_configuration_write_lease(root):
                            config.write_text("cooperating-operator-change\n", encoding="utf-8")
                return original_replace(path, target)

            runner = _Runner(fail_when=("exec", "-T", "api"))
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                with patch.object(Path, "replace", new=replace):
                    with self.assertRaisesRegex(deployment.R2CutoverDeploymentError, "baseline was restored"):
                        deployment.deploy_r2_cutover(
                            repository_root=root,
                            backup=backup,
                            confirm=True,
                            drain_seconds=0,
                            runner=runner,
                            correlation_id=CORRELATION_ID,
                        )

            self.assertEqual(attempted, [True])
            self.assertEqual(config.read_bytes(), (backup.path / "config" / "librarian.json").read_bytes())

    def test_active_record_is_idempotent_and_does_not_repeat_compose(self) -> None:
        deployment = _load_deployment()
        with _backup(deployment) as (root, backup):
            (backup.path / deployment.DEPLOYMENT_RECORD_NAME).write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "release_sha": RELEASE_SHA,
                        "correlation_id": CORRELATION_ID,
                        "state": "r2_active",
                    }
                ),
                encoding="utf-8",
            )
            runner = _Runner()
            with patch.object(deployment, "_require_clean_release", return_value=RELEASE_SHA):
                result = deployment.deploy_r2_cutover(
                    repository_root=root,
                    backup=backup,
                    confirm=True,
                    runner=runner,
                )

        self.assertTrue(result.already_active)
        self.assertEqual(result.correlation_id, CORRELATION_ID)
        self.assertEqual(runner.calls, [])


class _Call:
    def __init__(self, command: tuple[str, ...], environment: dict[str, str]) -> None:
        self.command = command
        self.environment = environment


class _Runner:
    def __init__(
        self,
        *,
        fail_when: tuple[str, ...] | None = None,
        fail_after: int = 0,
        fail_rollback: bool = False,
        before_failure=None,
        fail_at: int = 1,
    ) -> None:
        self.calls: list[_Call] = []
        self.fail_when = fail_when
        self.fail_after = fail_after
        self.fail_rollback = fail_rollback
        self.before_failure = before_failure
        self.fail_at = fail_at
        self._failures = 0
        self._matching_calls = 0

    def __call__(self, command, root, environment):
        command_tuple = tuple(command)
        self.calls.append(_Call(command_tuple, dict(environment)))
        if self.fail_when and _contains(command_tuple, self.fail_when):
            self._matching_calls += 1
            if self._matching_calls >= self.fail_at:
                if self.before_failure is not None:
                    self.before_failure()
                self._failures += 1
                return _completed(command_tuple, 1)
        if self.fail_rollback and self._failures >= self.fail_after and command_tuple[-2:] == ("down", "--remove-orphans"):
            return _completed(command_tuple, 1)
        if _contains(command_tuple, ("images", "--format", "json")):
            return _completed(
                command_tuple,
                0,
                stdout=json.dumps(
                    [
                        {"Repository": "librarian-api", "Tag": "latest", "ID": "sha256:api"},
                        {"Repository": "librarian-web", "Tag": "latest", "ImageID": "sha256:web"},
                    ]
                ),
            )
        return _completed(command_tuple, 0)


def _backup(deployment):
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    backup_path = root / "backups" / "r2-cutover"
    shutil.copytree(FIXTURE_CONFIG, backup_path / "config")
    (backup_path / "cutover.json").write_text(
        json.dumps({"schema_version": 1, "release_sha": RELEASE_SHA}) + "\n",
        encoding="utf-8",
    )
    # Every test uses a distinct pretend repository and ignored configuration
    # tree.  No test may inspect or modify REPO_ROOT/config or its credentials.
    shutil.copytree(FIXTURE_CONFIG, root / "config")
    backup = deployment.R2CutoverBackup(release_sha=RELEASE_SHA, path=backup_path)

    class _Context:
        def __enter__(self):
            return root, backup

        def __exit__(self, *unused):
            directory.cleanup()

    return _Context()

def _completed(command, returncode, stdout=""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def _contains(command: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    return any(command[index : index + len(sequence)] == sequence for index in range(len(command)))


def _index(commands: list[tuple[str, ...]], sequence: tuple[str, ...]) -> int:
    return next(index for index, command in enumerate(commands) if _contains(command, sequence))


def _load_deployment():
    spec = importlib.util.spec_from_file_location(
        f"r2_cutover_deployment_{id(DEPLOYMENT_PATH)}", DEPLOYMENT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
