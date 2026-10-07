"""Tests for the single-file, role-bound Docker broker startup preflight."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.broker_client_admission import (
    BROKER_CREDENTIAL_FILE_ENV,
    EXECUTION_PRINCIPAL_ENV,
)
from librarian_contracts.broker_client_preflight import (
    BROKER_RUNTIME_CONFIG_PATH,
    BrokerClientPreflightError,
    preflight_broker_client,
)
from librarian_contracts.runtime_config import (
    build_broker_client_runtime_config,
    serialize_broker_client_runtime_config,
)


class BrokerClientPreflightTests(unittest.TestCase):
    """R2 callers must fail before channel construction on any bad local state."""

    def test_uses_one_fixed_runtime_file_and_matching_secret_mount(self) -> None:
        self.assertEqual(BROKER_RUNTIME_CONFIG_PATH, Path("/config/librarian.json"))

        with _client_mounts("api") as mounts:
            preflight = preflight_broker_client(environ=mounts.environment)

        self.assertEqual(preflight.runtime_config.credential_role, "api")
        self.assertEqual(preflight.admission.principal, "api")
        self.assertEqual(preflight.admission.credential_file.name, "codex-broker-api")

    def test_invalid_or_symlinked_config_fails_before_secret_admission(self) -> None:
        with _client_mounts("api") as mounts:
            mounts.config_path.write_text("not JSON", encoding="utf-8")
            with (
                patch(
                    "librarian_contracts.broker_client_preflight.validate_broker_client_admission",
                    side_effect=AssertionError("bad configuration must not inspect a secret"),
                ) as admission,
                self.assertRaisesRegex(BrokerClientPreflightError, "configuration is invalid"),
            ):
                preflight_broker_client(environ=mounts.environment)
            admission.assert_not_called()

            mounts.config_path.unlink()
            alternate_config = mounts.config_path.parent / "alternate-librarian.json"
            alternate_config.write_text("{}", encoding="utf-8")
            mounts.config_path.symlink_to(alternate_config)
            with self.assertRaisesRegex(BrokerClientPreflightError, "configuration is invalid"):
                preflight_broker_client(environ=mounts.environment)

    def test_wrong_environment_role_fails_before_opening_the_matching_secret(self) -> None:
        with _client_mounts("api") as mounts:
            environment = {**mounts.environment, EXECUTION_PRINCIPAL_ENV: "evaluator"}
            with self.assertRaisesRegex(BrokerClientPreflightError, "credential admission failed"):
                preflight_broker_client(environ=environment)


class _client_mounts:
    """Patch the immutable container paths with hermetic test mounts."""

    def __init__(self, role: str) -> None:
        self.role = role

    def __enter__(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self._temporary_directory.name)
        config_directory = root / "config"
        config_directory.mkdir()
        self.config_path = config_directory / "librarian.json"
        self.config_path.write_text(
            serialize_broker_client_runtime_config(
                build_broker_client_runtime_config(
                    model="gpt-5.6-sol",
                    answer_capability="quality",
                    credential_role=self.role,
                )
            ),
            encoding="utf-8",
        )

        secret_directory = root / "secrets"
        secret_directory.mkdir()
        credential_file = secret_directory / f"codex-broker-{self.role}"
        credential_file.write_text("not-observed-by-preflight\n", encoding="utf-8")
        credential_file.chmod(0o400)
        self.environment = {
            EXECUTION_PRINCIPAL_ENV: self.role,
            BROKER_CREDENTIAL_FILE_ENV: str(credential_file),
        }
        self._config_patcher = patch(
            "librarian_contracts.broker_client_preflight.BROKER_RUNTIME_CONFIG_PATH",
            self.config_path,
        )
        self._secret_patcher = patch(
            "librarian_contracts.broker_client_admission.BROKER_SECRETS_DIRECTORY",
            secret_directory,
        )
        self._config_patcher.start()
        self._secret_patcher.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._secret_patcher.stop()
        self._config_patcher.stop()
        self._temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
