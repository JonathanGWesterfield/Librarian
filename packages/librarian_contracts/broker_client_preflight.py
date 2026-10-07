"""One fail-closed startup preflight for future Docker broker clients.

M01 deliberately does not construct a channel.  This module joins the strict
single-file runtime configuration and exact secret-mount checks that every R2
caller must complete before constructing one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from librarian_contracts.broker_client_admission import (
    BrokerClientAdmission,
    BrokerClientAdmissionError,
    validate_broker_client_admission,
)
from librarian_contracts.runtime_config import (
    BrokerClientRuntimeConfig,
    RuntimeConfigError,
    load_broker_client_runtime_config,
)

BROKER_RUNTIME_CONFIG_PATH = Path("/config/librarian.json")


class BrokerClientPreflightError(ValueError):
    """A startup failure that must prevent construction of a broker target."""


@dataclass(frozen=True)
class BrokerClientPreflight:
    """The verified configuration and credential mount for one broker caller."""

    runtime_config: BrokerClientRuntimeConfig
    admission: BrokerClientAdmission


def preflight_broker_client(
    *, environ: Mapping[str, str] | None = None
) -> BrokerClientPreflight:
    """Load the only permitted config mount and prove its matching credential.

    The fixed path is intentional.  Compose provides precisely this generated,
    non-secret file to every R2 caller; accepting an environment-selected path
    would permit a caller to replace that deployment boundary with arbitrary
    host configuration.
    """

    try:
        runtime_config = load_broker_client_runtime_config(BROKER_RUNTIME_CONFIG_PATH)
    except RuntimeConfigError as error:
        raise BrokerClientPreflightError("broker runtime configuration is invalid") from error

    try:
        admission = validate_broker_client_admission(runtime_config, environ=environ)
    except BrokerClientAdmissionError as error:
        raise BrokerClientPreflightError("broker credential admission failed") from error

    return BrokerClientPreflight(runtime_config=runtime_config, admission=admission)
