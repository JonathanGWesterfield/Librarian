"""Regression coverage for the isolated answer-delivery contract-gate source tree."""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class AnswerDeliveryContractGateTests(unittest.TestCase):
    def test_release_archive_excludes_ignored_local_config_and_role_credentials(self) -> None:
        """The gate can expose only a tracked release tree to Docker."""

        with tempfile.TemporaryDirectory() as directory:
            archive = subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            ).stdout
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
                source.extractall(directory)
            staged = Path(directory)
            self.assertFalse((staged / "config" / "librarian.json").exists())
            self.assertFalse((staged / "config" / "secrets").exists())

    def test_gate_builds_and_mounts_only_the_temporary_archive_tree(self) -> None:
        gate = (REPO_ROOT / "scripts" / "run_answer_delivery_contract_gate.sh").read_text(
            encoding="utf-8"
        )
        dockerfile = (REPO_ROOT / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn('tar -x -C "$stage_dir"', gate)
        self.assertIn('-f \"$stage_dir/apps/api/Dockerfile\"', gate)
        self.assertIn("--target answer-delivery-contract-gate", gate)
        self.assertNotIn("--target test", gate)
        self.assertNotIn("--volume", gate)
        self.assertNotIn('"$root_dir:/workspace:ro"', gate)
        self.assertIn('rm -rf "$stage_dir"', gate)
        self.assertIn('tests.e2e.test_r2_compose_overlay', gate)
        self.assertIn("result.skipped", gate)
        self.assertIn("--workdir /app", gate)
        self.assertIn("PYTHONPATH=/app/packages", gate)
        self.assertIn("FROM test AS answer-delivery-contract-gate", dockerfile)
        self.assertIn("COPY proto/librarian/answer/v1/ proto/librarian/answer/v1/", dockerfile)
        self.assertIn(
            "COPY scripts/generate_contracts.sh scripts/prepare_r2_cutover.py "
            "scripts/resolve_provider_config.py scripts/",
            dockerfile,
        )


if __name__ == "__main__":
    unittest.main()
