"""Regression coverage for the documented R2 Compose acceptance entry point."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_SCRIPT = REPO_ROOT / "scripts/run_answer_delivery_compose.sh"
VALIDATOR_PATH = REPO_ROOT / "scripts/validate_answer_delivery_compose_reports.py"
REPORT_PROFILES = ["codex-broker", "workers", "metadata-workers", "evaluation"]
RESOLVER_PROFILES = ["config-resolver", *REPORT_PROFILES]


class AnswerDeliveryComposeScriptTests(unittest.TestCase):
    def test_report_validator_writes_and_accepts_the_exact_redacted_schema(self) -> None:
        validator = _load_validator()
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            validator.validate_reports(report_dir)
            self.assertEqual(
                {path.name for path in report_dir.iterdir()},
                {
                    "compose-summary.json",
                    "authorization.json",
                    "compatibility.json",
                    "cancellation.json",
                },
            )

    def test_report_validator_rejects_extra_files_unsafe_text_and_wrong_types(self) -> None:
        validator = _load_validator()
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            (report_dir / "unexpected.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

            with self.assertRaises(validator.ReportValidationError):
                validator._reject_unsafe_text({"note": "Bearer token"})
            (report_dir / "unexpected.json").unlink()

            authorization = report_dir / "authorization.json"
            authorization.write_text(
                '{"schema_version": 1, "principals_checked": true}\n', encoding="utf-8"
            )
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            authorization.write_text(
                authorization.read_text(encoding="utf-8").replace(
                    '"authorized_operations": 12', '"authorized_operations": 11'
                ).replace(
                    '"denied_operations": 24', '"denied_operations": 25'
                ),
                encoding="utf-8",
            )
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            authorization.write_text(
                authorization.read_text(encoding="utf-8").replace(
                    "unauthenticated_denied", "prompt"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

    def test_tracked_fixture_has_exactly_the_five_non_secret_test_credentials(self) -> None:
        secrets = REPO_ROOT / "tests/fixtures/answer_delivery/r2-compose/config/secrets"
        self.assertEqual(
            {path.name for path in secrets.iterdir()},
            {
                "codex-broker-api",
                "codex-broker-summary-worker",
                "codex-broker-metadata-worker",
                "codex-broker-evaluator",
                "codex-broker-health",
            },
        )
        for secret in secrets.iterdir():
            self.assertTrue(secret.read_text(encoding="utf-8").startswith("synthetic-"))

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required to render the live model")
    def test_resolver_bootstrap_profiles_render_the_real_r2_compose_model(self) -> None:
        resolver_profiles, report_profiles = _captured_harness_profiles()
        self.assertEqual(resolver_profiles, RESOLVER_PROFILES)
        self.assertEqual(report_profiles, REPORT_PROFILES)

        command = ["docker", "compose", "--project-name", "answer-delivery-profile-model"]
        for profile in resolver_profiles:
            command.extend(["--profile", profile])
        command.extend(
            [
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.r2.yml",
                "-f",
                "docker-compose.answer-delivery.yml",
                "config",
                "--format",
                "json",
            ]
        )

        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env={**os.environ, "LIBRARIAN_STACK_RELEASE_SHA": "a" * 40},
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        self.assertTrue(
            {"config-resolver", "api", "codex-broker", "summary-worker", "metadata-worker", "evaluator"}
            <= set(services),
            services.keys(),
        )

    def test_resolver_bootstrap_profile_is_separate_from_reported_r2_profiles(self) -> None:
        resolver_profiles, report_profiles = _captured_harness_profiles()

        self.assertEqual(resolver_profiles, RESOLVER_PROFILES)
        self.assertEqual(report_profiles, REPORT_PROFILES)


def _captured_harness_profiles() -> tuple[list[str], list[str]]:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        command_dir = workspace / "bin"
        command_dir.mkdir()
        call_log = workspace / "docker-calls.jsonl"
        _write_fake_docker(command_dir / "docker")
        _write_fake_git(command_dir / "git")

        environment = {
            **os.environ,
            "ANSWER_DELIVERY_REPORT_DIR": str(workspace / "reports"),
            "CALL_LOG": str(call_log),
            "PATH": f"{command_dir}{os.pathsep}{os.environ['PATH']}",
            "VERIFY_PROJECT": "answer-delivery-profile-proof",
        }
        result = subprocess.run(
            ["bash", str(COMPOSE_SCRIPT)],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 23:
            raise AssertionError(result.stderr)

        compose_calls = [
            command for command in _recorded_commands(call_log) if command and command[0] == "compose"
        ]
        resolver_call = next(
            command
            for command in compose_calls
            if command[-4:] == ["run", "--rm", "--build", "config-resolver"]
        )
        rendered_config_call = next(
            command for command in compose_calls if "config" in command and "--format" in command
        )
        return _profiles(resolver_call), _profiles(rendered_config_call)


def _write_fake_docker(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            from pathlib import Path

            arguments = sys.argv[1:]
            with Path(os.environ["CALL_LOG"]).open("a", encoding="utf-8") as output:
                output.write(json.dumps(arguments) + "\\n")
            if arguments == ["info"]:
                raise SystemExit(0)
            if "run" in arguments and arguments[-1] == "config-resolver":
                runtime_dir = Path.cwd() / ".runtime" / "answer-delivery"
                runtime_dir.mkdir(parents=True, exist_ok=True)
                (runtime_dir / "librarian.compose.json").write_text("{}\\n", encoding="utf-8")
                raise SystemExit(0)
            if "config" in arguments and "--format" in arguments:
                raise SystemExit(23)
            raise SystemExit(0)
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_git(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys

            arguments = sys.argv[1:]
            if arguments == ["rev-parse", "HEAD"]:
                print("a" * 40)
            elif arguments != ["status", "--porcelain"]:
                raise SystemExit(1)
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _recorded_commands(path: Path) -> list[list[str]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _profiles(command: list[str]) -> list[str]:
    return [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--profile"]


if __name__ == "__main__":
    unittest.main()


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        f"answer_delivery_report_validator_{id(VALIDATOR_PATH)}", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe() -> dict[str, object]:
    return {
        "compose_summary": {
            "schema_version": 1,
            "broker_health": {
                "authenticated_health": "serving",
                "capabilities_verified": True,
                "generate_denied": True,
                "caller_health_denied": True,
            },
            "fake_provider": "synthetic",
            "http_listener": "absent",
        },
        "authorization": {
            "schema_version": 1,
            "principals_checked": 4,
            "authorized_operations": 12,
            "denied_operations": 24,
            "unauthenticated_denied": True,
        },
        "compatibility": {
            "schema_version": 1,
            "contract_mismatches": ["descriptor", "major", "minor", "release_sha"],
            "generate_release_mismatch_denied": True,
            "unhealthy_broker_denied": True,
            "deadline_denied": True,
            "queue_full_denied": True,
        },
        "cancellation": {
            "schema_version": 1,
            "rpc_cancelled": True,
            "process_group_reaped": True,
        },
    }
