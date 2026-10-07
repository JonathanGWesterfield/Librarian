"""Pre-channel admission for an R2 Docker Codex-broker client.

The future gRPC client calls this after parsing its sanitized runtime file and
before it constructs a target or channel.  It deliberately checks the mounted
credential file without reading its value, so this guard cannot turn a secret
into configuration or diagnostics.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from librarian_contracts.runtime_config import (
    BrokerClientRuntimeConfig,
    RuntimeConfigError,
    serialize_broker_client_runtime_config,
)

EXECUTION_PRINCIPAL_ENV = "LIBRARIAN_EXECUTION_PRINCIPAL"
BROKER_CREDENTIAL_FILE_ENV = "LIBRARIAN_BROKER_CREDENTIAL_FILE"
BROKER_SECRETS_DIRECTORY = Path("/run/secrets")
_SECRET_FILE_PREFIX = "codex-broker-"


class BrokerClientAdmissionError(ValueError):
    """Raised before a process may construct a private broker connection."""


@dataclass(frozen=True)
class BrokerClientAdmission:
    """The verified role and exact secret mount for one future broker client."""

    principal: str
    credential_file: Path


def validate_broker_client_admission(
    runtime_config: BrokerClientRuntimeConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> BrokerClientAdmission:
    """Require runtime role, environment role, and one exact secret to agree.

    The path comparison intentionally occurs before filesystem access.  A host
    process can forge the principal environment variable, but cannot satisfy
    the fixed `/run/secrets/codex-broker-<role>` mount check.
    """

    # Reuse the strict runtime-config validation for manually constructed as
    # well as parsed dataclasses. The result is intentionally discarded.
    try:
        serialize_broker_client_runtime_config(runtime_config)
    except RuntimeConfigError as error:
        raise BrokerClientAdmissionError("runtime configuration is invalid") from error

    environment = os.environ if environ is None else environ
    principal = environment.get(EXECUTION_PRINCIPAL_ENV)
    credential_file = environment.get(BROKER_CREDENTIAL_FILE_ENV)
    expected_file = _expected_credential_file(runtime_config.credential_role)

    if principal != runtime_config.credential_role:
        raise BrokerClientAdmissionError("execution principal does not match runtime role")
    if credential_file != str(expected_file):
        raise BrokerClientAdmissionError("credential file does not match runtime role")

    _validate_secret_file(expected_file)
    return BrokerClientAdmission(
        principal=runtime_config.credential_role,
        credential_file=expected_file,
    )


def _expected_credential_file(role: str) -> Path:
    return BROKER_SECRETS_DIRECTORY / f"{_SECRET_FILE_PREFIX}{role}"


def _validate_secret_file(path: Path) -> None:
    """Prove the exact mount is a readable regular file without reading it."""

    try:
        initial_stat = path.lstat()
    except OSError as error:
        raise BrokerClientAdmissionError("credential file is unavailable") from error
    if stat.S_ISLNK(initial_stat.st_mode):
        raise BrokerClientAdmissionError("credential file must not be a symlink")
    if not stat.S_ISREG(initial_stat.st_mode):
        raise BrokerClientAdmissionError("credential file must be a regular file")

    open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, open_flags)
    except OSError as error:
        raise BrokerClientAdmissionError("credential file is unavailable") from error
    try:
        try:
            opened_stat = os.fstat(descriptor)
        except OSError as error:
            raise BrokerClientAdmissionError("credential file is unavailable") from error
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(opened_stat.st_mode):
        raise BrokerClientAdmissionError("credential file must be a regular file")
