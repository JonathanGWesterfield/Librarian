"""Regression tests for one-shot Docker Ollama startup in the Bash launcher.

Examples:
    python3 -m unittest tests.e2e.test_start_local_launcher
    python3 -m unittest discover -s tests/e2e -p 'test_start_local_launcher.py'
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class StartLocalLauncherTests(unittest.TestCase):
    """Exercise launcher decisions with a deterministic fake Docker CLI."""

    def test_running_initializer_must_exit_successfully_before_api_starts(self) -> None:
        """A still-running one-shot service is polled instead of treated as ready."""
        completed, calls = self._run_launcher("running-then-success")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Stack started", completed.stdout)
        self.assertGreaterEqual(calls.count("inspect --format"), 2)
        self.assertIn("exec -T ollama ollama list", calls)
        self.assertIn("up -d api web", calls)

    def test_nonzero_initializer_exit_stops_before_api_startup(self) -> None:
        """A failed pull prints diagnostics and prevents an unusable stack."""
        completed, calls = self._run_launcher("failure")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ollama-init exited with code 7", completed.stderr)
        self.assertIn("ollama-init logs", completed.stderr)
        self.assertNotIn("up -d api web", calls)

    def _run_launcher(self, initializer_state: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "config").mkdir()
            (root / "config" / "librarian.json").write_text("{}\n", encoding="utf-8")
            shutil.copy2(REPO_ROOT / "scripts" / "start_local.sh", root / "scripts")
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            _write_fake_docker(fake_bin / "docker")
            (fake_bin / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            for command in fake_bin.iterdir():
                command.chmod(0o755)

            environment = os.environ | {
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "OLLAMA_INIT_FAKE_STATE": initializer_state,
            }
            completed = subprocess.run(
                ["bash", "scripts/start_local.sh", "--no-build"],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            calls = (root / "docker.calls").read_text(encoding="utf-8")
        return completed, calls


def _write_fake_docker(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$PWD/docker.calls"

if [[ "$*" == "compose version" || "$1" == "info" ]]; then
  exit 0
fi
if [[ "$*" == *"config-resolver run"* ]]; then
  mkdir -p .runtime
  printf '%s\\n' '{' '  "docker_ollama_enabled": true,' '  "api_port": 8000,' '  "web_port": 3000' '}' > .runtime/librarian.state.json
  printf '%s\\n' '{' '  "services": {' '    "ollama-init": {' '      "environment": {' '        "OLLAMA_INIT_MODELS": "all-minilm,qwen2.5:1.5b"' '      }' '    }' '  }' '}' > .runtime/librarian.compose.json
  exit 0
fi
if [[ "$*" == *"ps --all --quiet ollama-init"* ]]; then
  printf '%s\\n' 'fake-ollama-init'
  exit 0
fi
if [[ "$1" == "inspect" ]]; then
  case "${OLLAMA_INIT_FAKE_STATE:?}" in
    running-then-success)
      if [[ ! -f .runtime/inspect-called ]]; then
        touch .runtime/inspect-called
        printf '%s\\n' 'running 0'
      else
        printf '%s\\n' 'exited 0'
      fi
      ;;
    failure) printf '%s\\n' 'exited 7' ;;
  esac
  exit 0
fi
if [[ "$*" == *"exec -T ollama ollama list"* ]]; then
  printf '%s\\n' 'NAME ID SIZE MODIFIED'
  printf '%s\\n' 'all-minilm:latest abc 1 MB now'
  printf '%s\\n' 'qwen2.5:1.5b def 1 MB now'
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
