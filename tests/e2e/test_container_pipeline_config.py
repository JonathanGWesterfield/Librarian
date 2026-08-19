import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class ContainerPipelineConfigTests(unittest.TestCase):
    def test_runtime_and_test_docker_targets_are_separated(self) -> None:
        """Verify the deployable image does not copy test/evaluation harnesses."""
        dockerfile = (REPO_ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")

        runtime, test = dockerfile.split("FROM runtime AS test", maxsplit=1)
        self.assertIn("FROM python:3.12-slim AS runtime", runtime)
        self.assertNotIn("COPY tests tests", runtime)
        self.assertNotIn("evaluate_retrieval.py", runtime)
        self.assertIn("COPY tests tests", test)
        self.assertIn("COPY scripts/evaluate_retrieval.py scripts/verify_compose.py", test)

    def test_ci_builds_targets_from_the_api_dockerfile(self) -> None:
        """Verify CI uses the Dockerfile that defines the runtime/test targets."""
        workflow = (REPO_ROOT / ".github/workflows/tests.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "docker build -f apps/api/Dockerfile --target runtime", workflow
        )
        self.assertIn(
            "docker build -f apps/api/Dockerfile --target test", workflow
        )

    def test_verify_overlay_is_profile_gated_and_uses_runtime_api(self) -> None:
        """Verify standard Compose startup cannot launch the one-shot verifier."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        overlay = (REPO_ROOT / "docker-compose.verify.yml").read_text(encoding="utf-8")

        self.assertIn("target: runtime", compose)
        self.assertIn("- verify", overlay)
        self.assertIn("target: test", overlay)
        self.assertIn("http://api:8000", overlay)
        self.assertIn("./tests/fixtures/epubs:/books:ro", overlay)
        self.assertIn("verify-opensearch-data:/usr/share/opensearch/data", overlay)
        self.assertNotIn("\n      - opensearch-data:", overlay)
        self.assertNotIn("Epub-Books", overlay)

    def test_verification_runner_waits_for_dependencies_then_runs_verifier(self) -> None:
        """Verify a successful ollama-init exit cannot abort the evaluator."""
        runner = (REPO_ROOT / "scripts/run_compose_verification.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("--project-name \"$project_name\"", runner)
        self.assertIn("up --build --detach --wait opensearch ollama", runner)
        self.assertIn("up --build --detach ollama-init", runner)
        self.assertIn("wait ollama-init", runner)
        self.assertIn("up --build --detach --wait api", runner)
        self.assertIn("run --build --rm --no-deps verifier", runner)
        self.assertNotIn("--profile verify up", runner)
        self.assertNotIn("--abort-on-container-exit", runner)
        self.assertIn("down --volumes --remove-orphans", runner)

    def test_preflight_help_is_available_without_docker(self) -> None:
        """Verify users can discover the configurable verifier memory threshold."""
        completed = subprocess.run(
            ["bash", "scripts/verify_preflight.sh", "--help"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("--minimum-gb", completed.stdout)
        self.assertIn("LIBRARIAN_VERIFY_MIN_MEMORY_GB", completed.stdout)
