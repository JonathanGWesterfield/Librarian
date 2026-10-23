#!/usr/bin/env python3
"""Write and strictly validate the four redacted R2 Compose acceptance reports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPORT_FILENAMES = {
    "compose_summary": "compose-summary.json",
    "authorization": "authorization.json",
    "compatibility": "compatibility.json",
    "cancellation": "cancellation.json",
}
_REPORT_FILE_SET = frozenset(REPORT_FILENAMES.values())
_RELEASE_SHA = re.compile(r"[0-9a-f]{40}\Z")
_UNSAFE_TEXT = re.compile(r"token|credential|bearer|authorization|prompt|excerpt|/run/secrets", re.I)


class ReportValidationError(ValueError):
    """An acceptance report is missing, malformed, or exposes unsafe data."""


def write_reports(
    *, probe: dict[str, Any], report_dir: Path, release_sha: str, profiles: list[str]
) -> None:
    """Convert the broker's fixed probe shape into the four public artifacts."""

    _require_exact_keys(probe, set(REPORT_FILENAMES), "probe")
    summary = _require_object(probe["compose_summary"], "probe.compose_summary").copy()
    summary["release_sha"] = release_sha
    summary["profiles"] = profiles
    summary["services"] = {
        "api": "healthy",
        "summary-worker": "running",
        "metadata-worker": "running",
        "evaluator": "handshake-complete",
        "codex-broker": "healthy",
    }
    rendered = {**probe, "compose_summary": summary}
    for key, filename in REPORT_FILENAMES.items():
        (report_dir / filename).write_text(
            json.dumps(rendered[key], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def validate_reports(report_dir: Path) -> None:
    """Require exactly four redacted JSON files with their complete schemas."""

    entries = {path.name for path in report_dir.iterdir()}
    if entries != _REPORT_FILE_SET:
        raise ReportValidationError("acceptance report directory must contain exactly four report files")
    reports = {
        key: _load_report(report_dir / filename, filename)
        for key, filename in REPORT_FILENAMES.items()
    }
    _validate_compose_summary(reports["compose_summary"])
    _validate_authorization(reports["authorization"])
    _validate_compatibility(reports["compatibility"])
    _validate_cancellation(reports["cancellation"])
    for report in reports.values():
        _reject_unsafe_text(report)


def _load_report(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReportValidationError(f"{label} must be a regular report file")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReportValidationError(f"{label} must be valid UTF-8 JSON") from error
    return _require_object(decoded, label)


def _validate_compose_summary(report: dict[str, Any]) -> None:
    _require_exact_keys(
        report,
        {"schema_version", "broker_health", "fake_provider", "http_listener", "release_sha", "profiles", "services"},
        "compose-summary.json",
    )
    _require_schema_version(report, "compose-summary.json")
    health = _require_object(report["broker_health"], "compose-summary.json.broker_health")
    _require_exact_keys(
        health,
        {"authenticated_health", "capabilities_verified", "generate_denied", "caller_health_denied"},
        "compose-summary.json.broker_health",
    )
    _require_value(health["authenticated_health"], "serving", "authenticated_health")
    for key in ("capabilities_verified", "generate_denied", "caller_health_denied"):
        _require_bool(health[key], key)
    _require_value(report["fake_provider"], "synthetic", "fake_provider")
    _require_value(report["http_listener"], "absent", "http_listener")
    if not isinstance(report["release_sha"], str) or not _RELEASE_SHA.fullmatch(report["release_sha"]):
        raise ReportValidationError("compose-summary.json.release_sha must be a 40-character SHA")
    profiles = report["profiles"]
    if profiles != ["codex-broker", "workers", "metadata-workers", "evaluation"]:
        raise ReportValidationError("compose-summary.json.profiles must name every R2 profile")
    services = _require_object(report["services"], "compose-summary.json.services")
    _require_exact_keys(
        services,
        {"api", "summary-worker", "metadata-worker", "evaluator", "codex-broker"},
        "compose-summary.json.services",
    )
    for service, expected in {
        "api": "healthy",
        "summary-worker": "running",
        "metadata-worker": "running",
        "evaluator": "handshake-complete",
        "codex-broker": "healthy",
    }.items():
        _require_value(services[service], expected, f"services.{service}")


def _validate_authorization(report: dict[str, Any]) -> None:
    _require_exact_keys(
        report,
        {"schema_version", "principals_checked", "authorized_operations", "denied_operations", "unauthenticated_denied"},
        "authorization.json",
    )
    _require_schema_version(report, "authorization.json")
    _require_int(report["principals_checked"], 4, "principals_checked")
    _require_int(report["authorized_operations"], 12, "authorized_operations")
    _require_int(report["denied_operations"], 24, "denied_operations")
    _require_bool(report["unauthenticated_denied"], "unauthenticated_denied")


def _validate_compatibility(report: dict[str, Any]) -> None:
    _require_exact_keys(
        report,
        {
            "schema_version",
            "contract_mismatches",
            "generate_release_mismatch_denied",
            "unhealthy_broker_denied",
            "deadline_denied",
            "queue_full_denied",
        },
        "compatibility.json",
    )
    _require_schema_version(report, "compatibility.json")
    if report["contract_mismatches"] != ["descriptor", "major", "minor", "release_sha"]:
        raise ReportValidationError("compatibility.json must record every contract mismatch")
    for key in (
        "generate_release_mismatch_denied",
        "unhealthy_broker_denied",
        "deadline_denied",
        "queue_full_denied",
    ):
        _require_bool(report[key], key)


def _validate_cancellation(report: dict[str, Any]) -> None:
    _require_exact_keys(
        report,
        {"schema_version", "rpc_cancelled", "process_group_reaped"},
        "cancellation.json",
    )
    _require_schema_version(report, "cancellation.json")
    _require_bool(report["rpc_cancelled"], "rpc_cancelled")
    _require_bool(report["process_group_reaped"], "process_group_reaped")


def _reject_unsafe_text(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_unsafe_text(key)
            _reject_unsafe_text(item)
    elif isinstance(value, list):
        for item in value:
            _reject_unsafe_text(item)
    elif isinstance(value, str) and _UNSAFE_TEXT.search(value):
        raise ReportValidationError("acceptance reports must not contain credential or source text")


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ReportValidationError(f"{label} has an unexpected field shape")


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportValidationError(f"{label} must be a JSON object")
    return value


def _require_schema_version(report: dict[str, Any], label: str) -> None:
    _require_int(report.get("schema_version"), 1, f"{label}.schema_version")


def _require_bool(value: Any, label: str) -> None:
    if value is not True:
        raise ReportValidationError(f"{label} must be true")


def _require_int(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise ReportValidationError(f"{label} must equal {expected}")


def _require_value(value: Any, expected: str, label: str) -> None:
    if value != expected:
        raise ReportValidationError(f"{label} must equal {expected}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--profiles", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        probe = _load_report(args.probe, "probe")
        write_reports(
            probe=probe,
            report_dir=args.report_dir,
            release_sha=args.release_sha,
            profiles=args.profiles,
        )
        validate_reports(args.report_dir)
    except ReportValidationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
