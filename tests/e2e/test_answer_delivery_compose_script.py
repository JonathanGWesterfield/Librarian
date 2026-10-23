"""Regression coverage for the documented R2 Compose acceptance entry point."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts/validate_answer_delivery_compose_reports.py"


class AnswerDeliveryComposeScriptTests(unittest.TestCase):
    def test_report_validator_writes_and_accepts_the_exact_redacted_schema(self) -> None:
        validator = _load_validator()
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            validator.validate_reports(report_dir)
            self.assertEqual(
                {path.name for path in report_dir.iterdir()},
                {
                    "compose-summary.json",
                    "authorization.json",
                    "compatibility.json",
                    "cancellation.json",
                },
            )

    def test_report_validator_rejects_extra_files_unsafe_text_and_wrong_types(self) -> None:
        validator = _load_validator()
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            (report_dir / "unexpected.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

            with self.assertRaises(validator.ReportValidationError):
                validator._reject_unsafe_text({"note": "Bearer token"})
            (report_dir / "unexpected.json").unlink()

            authorization = report_dir / "authorization.json"
            authorization.write_text(
                '{"schema_version": 1, "principals_checked": true}\n', encoding="utf-8"
            )
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            authorization.write_text(
                authorization.read_text(encoding="utf-8").replace(
                    '"authorized_operations": 12', '"authorized_operations": 11'
                ).replace(
                    '"denied_operations": 24', '"denied_operations": 25'
                ),
                encoding="utf-8",
            )
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

            validator.write_reports(
                probe=_probe(),
                report_dir=report_dir,
                release_sha="a" * 40,
                profiles=["codex-broker", "workers", "metadata-workers", "evaluation"],
            )
            authorization.write_text(
                authorization.read_text(encoding="utf-8").replace(
                    "unauthenticated_denied", "prompt"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(validator.ReportValidationError):
                validator.validate_reports(report_dir)

    def test_tracked_fixture_has_exactly_the_five_non_secret_test_credentials(self) -> None:
        secrets = REPO_ROOT / "tests/fixtures/answer_delivery/r2-compose/config/secrets"
        self.assertEqual(
            {path.name for path in secrets.iterdir()},
            {
                "codex-broker-api",
                "codex-broker-summary-worker",
                "codex-broker-metadata-worker",
                "codex-broker-evaluator",
                "codex-broker-health",
            },
        )
        for secret in secrets.iterdir():
            self.assertTrue(secret.read_text(encoding="utf-8").startswith("synthetic-"))


if __name__ == "__main__":
    unittest.main()


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        f"answer_delivery_report_validator_{id(VALIDATOR_PATH)}", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe() -> dict[str, object]:
    return {
        "compose_summary": {
            "schema_version": 1,
            "broker_health": {
                "authenticated_health": "serving",
                "capabilities_verified": True,
                "generate_denied": True,
                "caller_health_denied": True,
            },
            "fake_provider": "synthetic",
            "http_listener": "absent",
        },
        "authorization": {
            "schema_version": 1,
            "principals_checked": 4,
            "authorized_operations": 12,
            "denied_operations": 24,
            "unauthenticated_denied": True,
        },
        "compatibility": {
            "schema_version": 1,
            "contract_mismatches": ["descriptor", "major", "minor", "release_sha"],
            "generate_release_mismatch_denied": True,
            "unhealthy_broker_denied": True,
            "deadline_denied": True,
            "queue_full_denied": True,
        },
        "cancellation": {
            "schema_version": 1,
            "rpc_cancelled": True,
            "process_group_reaped": True,
        },
    }
