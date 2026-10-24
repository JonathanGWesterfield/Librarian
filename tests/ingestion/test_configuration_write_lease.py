"""Tests for the shared configuration-writer cutover lease."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
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

    @unittest.skipIf(os.name == "nt", "process-group interruption is a Unix behavior")
    def test_interrupted_wrapper_holds_lease_until_child_restores_config_and_exits(self) -> None:
        """A TERM sent only to the wrapper cannot open a write window.

        The child mimics the check/test cleanup trap: on TERM it restores the
        original config, then waits for this test to permit its final exit.
        A competing helper must still be denied during that window.
        """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config" / "librarian.json"
            config.parent.mkdir()
            original_config = b'{"provider": "local"}\n'
            config.write_bytes(original_config)
            source = root / "replacement.json"
            source.write_bytes(b'{"provider": "replacement"}\n')
            restored = root / "config-restored"
            started = root / "child-started"
            finish = root / "child-finish"
            cleanup_child = root / "cleanup_child.py"
            cleanup_child.write_text(
                "\n".join(
                    (
                        "import signal",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "root = Path(sys.argv[1])",
                        "config = root / 'config' / 'librarian.json'",
                        "config.write_bytes(b'{\\\"provider\\\": \\\"temporary\\\"}\\n')",
                        "(root / 'cleanup-child-pid').write_text(str(__import__('os').getpid()))",
                        "(root / 'child-started').touch()",
                        "def restore(_signum, _frame):",
                        "    config.write_bytes(b'{\\\"provider\\\": \\\"local\\\"}\\n')",
                        "    (root / 'config-restored').touch()",
                        "    while not (root / 'child-finish').exists():",
                        "        time.sleep(0.01)",
                        "    raise SystemExit(143)",
                        "signal.signal(signal.SIGTERM, restore)",
                        "while True:",
                        "    time.sleep(0.01)",
                    )
                ),
                encoding="utf-8",
            )
            leader = root / "leader.py"
            leader.write_text(
                "\n".join(
                    (
                        "import signal",
                        "import subprocess",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "root = Path(sys.argv[1])",
                        "subprocess.Popen([sys.executable, str(root / 'cleanup_child.py'), str(root)])",
                        "(root / 'leader-pid').write_text(str(__import__('os').getpid()))",
                        "def stop(_signum, _frame):",
                        "    raise SystemExit(143)",
                        "signal.signal(signal.SIGTERM, stop)",
                        "while True:",
                        "    time.sleep(0.01)",
                    )
                ),
                encoding="utf-8",
            )
            wrapper = subprocess.Popen(
                [
                    sys.executable,
                    str(LEASE_HELPER),
                    "--root",
                    str(root),
                    "--",
                    sys.executable,
                    str(leader),
                    str(root),
                ]
            )
            try:
                self._wait_for_path(started)
                os.kill(wrapper.pid, signal.SIGTERM)
                self._wait_for_path(restored)

                self.assertIsNone(wrapper.poll(), "wrapper released the lease before child cleanup")
                competing_writer = subprocess.run(
                    [
                        sys.executable,
                        str(LEASE_HELPER),
                        "--root",
                        str(root),
                        "--copy-file",
                        str(source),
                        str(config),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(competing_writer.returncode, 2)
                self.assertEqual(config.read_bytes(), original_config)

                finish.touch()
                self.assertEqual(wrapper.wait(timeout=10), 143)
                self.assertEqual(config.read_bytes(), original_config)
            finally:
                finish.touch(exist_ok=True)
                if wrapper.poll() is None:
                    wrapper.send_signal(signal.SIGTERM)
                    wrapper.wait(timeout=10)
                for pid_file in (root / "leader-pid", root / "cleanup-child-pid"):
                    if pid_file.exists():
                        try:
                            os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGTERM)
                        except ProcessLookupError:
                            pass

    def _wait_for_path(self, path: Path, *, timeout_seconds: float = 10.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(0.01)
        self.fail(f"timed out waiting for {path.name}")


if __name__ == "__main__":
    unittest.main()
