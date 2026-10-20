"""Regression coverage for the complete, profile-gated atomic R2 overlay."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.compose_security import validate_r2_compose_security

R2_COMPOSE_PROFILES = (
    "codex-broker",
    "workers",
    "metadata-workers",
    "evaluation",
)
R2_REQUIRED_SERVICES = {
    "api",
    "codex-broker",
    "summary-worker",
    "metadata-worker",
    "evaluator",
}
R2_API_SERVER_COMMAND = [
    "uvicorn",
    "librarian_api.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--app-dir",
    "apps/api",
]
R2_EVALUATOR_COMMAND = [
    "python",
    "scripts/evaluate_retrieval.py",
    "--output",
    "/tmp/librarian-evaluation-report.json",
    "--markdown-output",
    "/tmp/librarian-evaluation-report.md",
    "--llm-judge",
]
R2_EVALUATOR_ENTRYPOINT = [
    "python",
    "-m",
    "librarian_answer_adapters.r2_startup",
    "--principal",
    "evaluator",
    "--",
    *R2_EVALUATOR_COMMAND,
]


@unittest.skipUnless(shutil.which("docker"), "Docker Compose is required for overlay rendering")
class R2ComposeOverlayTests(unittest.TestCase):
    """The documented R2 invocation retains every principal's service."""

    def test_all_required_profiles_render_the_actual_r2_overlay(self) -> None:
        environment = {
            **os.environ,
            "LIBRARIAN_STACK_RELEASE_SHA": "a" * 40,
        }
        command = ["docker", "compose"]
        for profile in R2_COMPOSE_PROFILES:
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

        rendered = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        compose = json.loads(rendered.stdout)
        self.assertTrue(R2_REQUIRED_SERVICES.issubset(compose["services"]))
        self.assertEqual(
            compose["services"]["api"]["entrypoint"][-1],
            "--",
        )
        self.assertEqual(
            compose["services"]["api"]["command"],
            R2_API_SERVER_COMMAND,
        )
        self.assertEqual(
            compose["services"]["evaluator"]["entrypoint"],
            R2_EVALUATOR_ENTRYPOINT,
        )
        self.assertEqual(compose["services"]["evaluator"]["command"], [])
        validate_r2_compose_security(compose)


if __name__ == "__main__":
    unittest.main()
