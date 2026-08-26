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

    def test_ci_evaluation_uses_the_committed_test_json_configuration(self) -> None:
        """Verify the post-check evaluator does not need ignored local config.

        ``scripts/check.sh`` deliberately removes the temporary runtime
        configuration it uses for tests. GitHub Actions therefore installs the
        checked-in fixture just for its subsequent deterministic evaluation
        step, and removes it whether that evaluator succeeds or fails.
        """
        workflow = (REPO_ROOT / ".github/workflows/tests.yml").read_text(
            encoding="utf-8"
        )
        evaluation_step = workflow.split("- name: Publish evaluation summary", 1)[1].split(
            "- name: Upload evaluation reports", 1
        )[0]

        self.assertIn(
            "cp tests/fixtures/config/librarian.test.json config/librarian.json",
            evaluation_step,
        )
        self.assertIn("trap 'rm -f config/librarian.json' EXIT", evaluation_step)
        self.assertIn("python scripts/evaluate_retrieval.py --check", evaluation_step)
        self.assertNotIn("LIBRARIAN_", evaluation_step)

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

    def test_web_healthcheck_uses_the_container_ipv4_loopback(self) -> None:
        """Verify ``docker compose up --wait`` does not depend on localhost DNS."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        web_service = compose.split("  web:\n", maxsplit=1)[1].split(
            "  summary-worker:\n", maxsplit=1
        )[0]
        self.assertIn("http://127.0.0.1:8080/", web_service)
        self.assertNotIn("http://localhost:8080/", web_service)

    def test_local_launchers_wait_for_one_shot_ollama_and_verify_models(self) -> None:
        """Launchers must not mistake creation of ollama-init for successful pulls."""
        bash = (REPO_ROOT / "scripts" / "start_local.sh").read_text(encoding="utf-8")
        powershell = (REPO_ROOT / "scripts" / "start_local.ps1").read_text(
            encoding="utf-8"
        )

        for launcher in (bash, powershell):
            self.assertIn("ps --all --quiet ollama-init", launcher)
            self.assertIn("docker inspect", launcher)
            self.assertIn("OLLAMA_INIT_MODELS", launcher)
            self.assertIn("ollama list", launcher)
            self.assertIn("Timed out", launcher)
            self.assertNotIn("wait ollama-init", launcher)

    def test_powershell_initializer_failure_prints_diagnostics_before_throwing(self) -> None:
        """Stop-on-error must not suppress the service state and logs on Windows."""
        powershell = (REPO_ROOT / "scripts" / "start_local.ps1").read_text(
            encoding="utf-8"
        )
        diagnostic_body = powershell.split("function Show-OllamaInitDiagnostics", 1)[1].split(
            "function Wait-OllamaInit", 1
        )[0]
        self.assertIn("Write-Host", diagnostic_body)
        self.assertNotIn("Write-Error", diagnostic_body)
        self.assertIn("ps --all ollama-init", diagnostic_body)
        self.assertIn("logs --tail 100 ollama-init", diagnostic_body)

        wait_body = powershell.split("function Wait-OllamaInit", 1)[1].split(
            "function Confirm-DockerOllamaModels", 1
        )[0]
        for marker in (
            "ollama-init exited with code",
            "Timed out after",
        ):
            diagnostic_index = wait_body.index(marker)
            throw_index = wait_body.index("throw", diagnostic_index)
            self.assertLess(diagnostic_index, throw_index)
            self.assertIn(
                "Show-OllamaInitDiagnostics",
                wait_body[diagnostic_index:throw_index],
            )

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
        self.assertIn("VERIFY_MIN_MEMORY_GB", completed.stdout)
