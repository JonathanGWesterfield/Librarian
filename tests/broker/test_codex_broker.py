"""Contract tests for the internal Compose Codex broker.

Examples:
    scripts/test.sh tests.broker.test_codex_broker
    python3 -m unittest tests.broker.test_codex_broker
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))

from librarian_broker.main import app  # noqa: E402
from librarian_config.config import clear_librarian_config_cache  # noqa: E402


class CodexBrokerTests(unittest.TestCase):
    """The API container can use the broker without host credential mounts."""

    def tearDown(self) -> None:
        clear_librarian_config_cache()

    def test_authenticated_completion_uses_the_configured_codex_model(self) -> None:
        """The OpenAI-compatible route invokes only the JSON-selected model."""
        with self._configured_client() as client:
            completed = Mock(stdout="Exact source answer.\n")
            with patch(
                "librarian_broker.main.subprocess.run", return_value=completed
            ) as run:
                response = client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": "Bearer test-bridge-token"},
                    json={
                        "model": "gpt-5.6",
                        "messages": [
                            {"role": "system", "content": "Use only sources."},
                            {"role": "user", "content": "Question?"},
                        ],
                        "stream": False,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["choices"][0]["message"]["content"],
            "Exact source answer.",
        )
        self.assertEqual(
            run.call_args.args[0],
            [
                "codex",
                "exec",
                "--model",
                "gpt-5.6",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "-",
            ],
        )
        self.assertIn("SYSTEM:\nUse only sources.", run.call_args.kwargs["input"])

    def test_broker_rejects_missing_token_or_model_substitution(self) -> None:
        """Only the API/worker bearer token may call the configured model."""
        with self._configured_client() as client:
            missing_token = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-5.6", "messages": [{"role": "user", "content": "Q"}]},
            )
            wrong_model = client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer test-bridge-token"},
                json={"model": "other-model", "messages": [{"role": "user", "content": "Q"}]},
            )

        self.assertEqual(missing_token.status_code, 401)
        self.assertEqual(wrong_model.status_code, 400)

    def test_codex_login_failure_is_actionable_but_does_not_echo_stderr(self) -> None:
        """A broker request never leaks a CLI credential in its HTTP error body."""
        failure = __import__("subprocess").CalledProcessError(
            returncode=1,
            cmd=["codex"],
            stderr="token=should-not-leak",
        )
        with self._configured_client() as client:
            with patch("librarian_broker.main.subprocess.run", side_effect=failure):
                response = client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": "Bearer test-bridge-token"},
                    json={"model": "gpt-5.6", "messages": [{"role": "user", "content": "Q"}]},
                )

        self.assertEqual(response.status_code, 502)
        self.assertIn("codex-broker codex login", response.json()["detail"])
        self.assertNotIn("should-not-leak", response.text)

    def test_compose_keeps_codex_session_in_a_named_volume_only(self) -> None:
        """The Compose definition must never bind-mount host Codex credentials."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("codex-broker-session:/root/.codex", compose)
        self.assertIn("codex-broker-session:", compose)
        self.assertNotIn("- ~/.codex:", compose)

    def _configured_client(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        config_path = root / "librarian.json"
        payload = json.loads(
            (REPO_ROOT / "config" / "librarian.base.json").read_text(encoding="utf-8")
        )
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        secrets = root / "secrets"
        secrets.mkdir()
        (secrets / "codex-bridge-token.txt").write_text(
            "test-bridge-token\n", encoding="utf-8"
        )
        config_patch = patch(
            "librarian_config.config.default_config_path", return_value=config_path
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)
        clear_librarian_config_cache()
        return TestClient(app)


if __name__ == "__main__":
    unittest.main()
