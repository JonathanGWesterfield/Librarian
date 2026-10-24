"""Tests for the shared configuration-writer cutover lease."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEASE_HELPER = REPO_ROOT / "scripts" / "config_write_lease.py"

from librarian_config.write_lease import (
    CONFIG_WRITE_LEASE_FILENAME,
    ConfigurationWriteLeaseError,
    acquire_configuration_write_lease,
)


class ConfigurationWriteLeaseTests(unittest.TestCase):
    def test_exclusive_lease_rejects_another_librarian_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with acquire_configuration_write_lease(root) as lease:
                self.assertEqual(lease.path, (root / CONFIG_WRITE_LEASE_FILENAME).resolve())
                self.assertTrue(lease.path.is_file())
                with self.assertRaises(ConfigurationWriteLeaseError):
                    acquire_configuration_write_lease(root)
            with acquire_configuration_write_lease(root):
                pass

    def test_every_repository_script_that_writes_live_config_uses_the_lease_helper(self) -> None:
        writers = (
            REPO_ROOT / "scripts" / "start_local.sh",
            REPO_ROOT / "scripts" / "start_local.ps1",
            REPO_ROOT / "scripts" / "test.sh",
            REPO_ROOT / "scripts" / "check.sh",
            REPO_ROOT / ".github" / "workflows" / "tests.yml",
        )
        for writer in writers:
            with self.subTest(writer=writer.name):
                self.assertIn("config_write_lease.py", writer.read_text(encoding="utf-8"))

    def test_check_reuses_its_config_snapshot_for_the_nested_test_runner(self) -> None:
        """Only one cleanup handler may restore the user configuration."""

        check = (REPO_ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
        test = (REPO_ROOT / "scripts" / "test.sh").read_text(encoding="utf-8")

        self.assertIn("LIBRARIAN_TEST_CONFIG_INSTALLED=1 scripts/test.sh", check)
        self.assertIn("cleanup_test_config_on_signal", check)
        self.assertIn("trap 'cleanup_test_config_on_signal 143' TERM", check)
        self.assertIn('LIBRARIAN_TEST_CONFIG_INSTALLED:-}', test)
        self.assertIn("cleanup_test_config_on_signal", test)
        self.assertIn("trap 'cleanup_test_config_on_signal 143' TERM", test)

    def test_helper_refuses_a_live_config_copy_while_cutover_holds_the_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example.json"
            destination = root / "config" / "librarian.json"
            source.write_text('{"fixture": true}\n', encoding="utf-8")
            destination.parent.mkdir()
            destination.write_text('{"existing": true}\n', encoding="utf-8")
            with acquire_configuration_write_lease(root):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(LEASE_HELPER),
                        "--root",
                        str(root),
                        "--copy-file",
                        str(source),
                        str(destination),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(destination.read_text(encoding="utf-8"), '{"existing": true}\n')
            self.assertNotIn('{"fixture": true}', completed.stderr)


if __name__ == "__main__":
    unittest.main()
