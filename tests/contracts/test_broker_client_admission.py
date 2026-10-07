"""Tests for the R2 Docker broker client's pre-channel admission guard."""

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
    BrokerClientAdmissionError,
    validate_broker_client_admission,
)
from librarian_contracts.runtime_config import (
    CLIENT_CREDENTIAL_ROLES,
    build_broker_client_runtime_config,
)


class BrokerClientAdmissionTests(unittest.TestCase):
    """A role string alone must never make a process a broker client."""

    def test_each_client_role_requires_its_own_exact_regular_secret_file(self) -> None:
        with _secret_directory() as directory:
            for role in CLIENT_CREDENTIAL_ROLES:
                with self.subTest(role=role):
                    credential_file = directory / f"codex-broker-{role}"
                    credential_file.write_text("not-observed-by-guard\n", encoding="utf-8")
                    credential_file.chmod(0o400)

                    admission = validate_broker_client_admission(
                        _runtime_config(role),
                        environ=_environment(role, credential_file),
                    )

                    self.assertEqual(admission.principal, role)
                    self.assertEqual(admission.credential_file, credential_file)

    def test_forged_principal_or_another_roles_secret_fails_before_file_access(self) -> None:
        with _secret_directory() as directory:
            api_file = directory / "codex-broker-api"
            api_file.write_text("api-secret\n", encoding="utf-8")

            with patch(
                "librarian_contracts.broker_client_admission.os.open",
                side_effect=AssertionError("a mismatched caller must fail before opening a secret"),
            ) as open_file:
                with self.assertRaisesRegex(
                    BrokerClientAdmissionError,
                    "execution principal does not match runtime role",
                ):
                    validate_broker_client_admission(
                        _runtime_config("api"),
                        environ=_environment("evaluator", api_file),
                    )
                with self.assertRaisesRegex(
                    BrokerClientAdmissionError,
                    "credential file does not match runtime role",
                ):
                    validate_broker_client_admission(
                        _runtime_config("evaluator"),
                        environ=_environment("evaluator", api_file),
                    )

            open_file.assert_not_called()

    def test_host_forgery_missing_mount_symlink_and_directory_are_rejected(self) -> None:
        with _secret_directory() as directory:
            config = _runtime_config("api")
            expected_file = directory / "codex-broker-api"

            with self.assertRaisesRegex(BrokerClientAdmissionError, "unavailable"):
                validate_broker_client_admission(
                    config,
                    environ=_environment("api", expected_file),
                )

            target = directory / "actual-secret"
            target.write_text("api-secret\n", encoding="utf-8")
            expected_file.symlink_to(target)
            with self.assertRaisesRegex(BrokerClientAdmissionError, "must not be a symlink"):
                validate_broker_client_admission(
                    config,
                    environ=_environment("api", expected_file),
                )

            expected_file.unlink()
            expected_file.mkdir()
            with self.assertRaisesRegex(BrokerClientAdmissionError, "regular file"):
                validate_broker_client_admission(
                    config,
                    environ=_environment("api", expected_file),
                )

    def test_unreadable_secret_is_rejected_without_reading_its_contents(self) -> None:
        with _secret_directory() as directory:
            credential_file = directory / "codex-broker-api"
            credential_file.write_text("api-secret\n", encoding="utf-8")

            with (
                patch(
                    "librarian_contracts.broker_client_admission.os.open",
                    side_effect=PermissionError("denied"),
                ),
                self.assertRaisesRegex(BrokerClientAdmissionError, "unavailable"),
            ):
                validate_broker_client_admission(
                    _runtime_config("api"),
                    environ=_environment("api", credential_file),
                )

    def test_runtime_config_role_is_validated_before_environment_is_trusted(self) -> None:
        invalid_config = build_broker_client_runtime_config(
            model="gpt-5.6-sol",
            answer_capability="quality",
            credential_role="api",
        )
        object.__setattr__(invalid_config, "credential_role", "compose-health")

        with (
            self.assertRaisesRegex(BrokerClientAdmissionError, "runtime configuration is invalid"),
            _secret_directory() as directory,
        ):
            validate_broker_client_admission(
                invalid_config,
                environ=_environment(
                    "compose-health", directory / "codex-broker-compose-health"
                ),
            )


def _runtime_config(role: str):
    return build_broker_client_runtime_config(
        model="gpt-5.6-sol",
        answer_capability="quality",
        credential_role=role,
    )


def _environment(role: str, credential_file: Path) -> dict[str, str]:
    return {
        EXECUTION_PRINCIPAL_ENV: role,
        BROKER_CREDENTIAL_FILE_ENV: str(credential_file),
    }


class _secret_directory:
    """Replace the fixed Docker path with a hermetic test-only secrets mount."""

    def __enter__(self) -> Path:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self._temporary_directory.name)
        self._patcher = patch(
            "librarian_contracts.broker_client_admission.BROKER_SECRETS_DIRECTORY",
            self.path,
        )
        self._patcher.start()
        return self.path

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._patcher.stop()
        self._temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
