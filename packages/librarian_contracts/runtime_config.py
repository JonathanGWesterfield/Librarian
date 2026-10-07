"""Strict, non-secret gRPC client runtime configuration for the R2 migration.

The user-owned configuration is intentionally not this format: it can contain
host-relative paths to credential files. The R2 resolver will derive one
document from this module for each broker caller after it has read that input.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from librarian_contracts.stack_contract import CONTRACT_MAJOR, DEFAULT_CONTRACT_MINOR

RUNTIME_CONFIG_VERSION = 1
BROKER_TRANSPORT = "grpc"
DOCKER_BROKER_TARGET = "dns:///codex-broker:50051"
CLIENT_CREDENTIAL_ROLES = frozenset(
    {"api", "summary-worker", "metadata-worker", "evaluator"}
)
ANSWER_CAPABILITIES = frozenset({"quality", "lightweight"})

_TOP_LEVEL_FIELDS = frozenset({"version", "generation", "services"})
_GENERATION_FIELDS = frozenset({"model", "answer_capability"})
_SERVICES_FIELDS = frozenset({"codex_broker"})
_BROKER_FIELDS = frozenset(
    {
        "transport",
        "target",
        "contract_major",
        "contract_minor",
        "credential_role",
    }
)


class RuntimeConfigError(ValueError):
    """Raised when a generated broker-client runtime configuration is unsafe."""


@dataclass(frozen=True)
class BrokerClientRuntimeConfig:
    """The complete, non-secret settings needed by one gRPC broker client."""

    model: str
    answer_capability: str
    target: str
    contract_major: int
    contract_minor: int
    credential_role: str


def build_broker_client_runtime_config(
    *,
    model: str,
    answer_capability: str,
    credential_role: str,
    target: str = DOCKER_BROKER_TARGET,
    contract_major: int = CONTRACT_MAJOR,
    contract_minor: int = DEFAULT_CONTRACT_MINOR,
) -> BrokerClientRuntimeConfig:
    """Build validated R2 client settings from resolver-owned values.

    Release SHA and descriptor digest remain in the immutable stack manifest,
    rather than being copied into mutable runtime configuration.
    """

    config = BrokerClientRuntimeConfig(
        model=model,
        answer_capability=answer_capability,
        target=target,
        contract_major=contract_major,
        contract_minor=contract_minor,
        credential_role=credential_role,
    )
    _validate(config)
    return config


def parse_broker_client_runtime_config(raw: str | bytes) -> BrokerClientRuntimeConfig:
    """Parse one canonical runtime document and reject hidden fields."""

    try:
        decoded = json.loads(raw, object_pairs_hook=_reject_duplicate_fields)
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeConfigError("broker runtime configuration must be valid JSON") from error

    root = _require_object(decoded, "broker runtime configuration")
    _require_exact_fields(root, _TOP_LEVEL_FIELDS, "broker runtime configuration")
    if (
        not isinstance(root["version"], int)
        or isinstance(root["version"], bool)
        or root["version"] != RUNTIME_CONFIG_VERSION
    ):
        raise RuntimeConfigError(f"runtime configuration version must be {RUNTIME_CONFIG_VERSION}")

    generation = _require_object(root["generation"], "generation")
    _require_exact_fields(generation, _GENERATION_FIELDS, "generation")
    services = _require_object(root["services"], "services")
    _require_exact_fields(services, _SERVICES_FIELDS, "services")
    broker = _require_object(services["codex_broker"], "services.codex_broker")
    _require_exact_fields(broker, _BROKER_FIELDS, "services.codex_broker")

    config = BrokerClientRuntimeConfig(
        model=generation["model"],
        answer_capability=generation["answer_capability"],
        target=broker["target"],
        contract_major=broker["contract_major"],
        contract_minor=broker["contract_minor"],
        credential_role=broker["credential_role"],
    )
    _validate(config)
    if broker["transport"] != BROKER_TRANSPORT:
        raise RuntimeConfigError(f"services.codex_broker.transport must be {BROKER_TRANSPORT}")
    return config


def serialize_broker_client_runtime_config(config: BrokerClientRuntimeConfig) -> str:
    """Render deterministic JSON suitable for one read-only container mount."""

    _validate(config)
    return json.dumps(
        {
            "version": RUNTIME_CONFIG_VERSION,
            "generation": {
                "model": config.model,
                "answer_capability": config.answer_capability,
            },
            "services": {
                "codex_broker": {
                    "transport": BROKER_TRANSPORT,
                    "target": config.target,
                    "contract_major": config.contract_major,
                    "contract_minor": config.contract_minor,
                    "credential_role": config.credential_role,
                }
            },
        },
        indent=2,
    ) + "\n"


def load_broker_client_runtime_config(path: Path) -> BrokerClientRuntimeConfig:
    """Load a generated runtime file without following configuration references."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeConfigError(
            f"could not read broker runtime configuration {path}: {error}"
        ) from error
    return parse_broker_client_runtime_config(raw)


def _validate(config: BrokerClientRuntimeConfig) -> None:
    _require_string(config.model, "generation.model")
    if (
        not isinstance(config.answer_capability, str)
        or config.answer_capability not in ANSWER_CAPABILITIES
    ):
        allowed = ", ".join(sorted(ANSWER_CAPABILITIES))
        raise RuntimeConfigError(f"generation.answer_capability must be one of: {allowed}")
    if config.target != DOCKER_BROKER_TARGET:
        raise RuntimeConfigError(
            f"services.codex_broker.target must be {DOCKER_BROKER_TARGET}"
        )
    if (
        not isinstance(config.contract_major, int)
        or isinstance(config.contract_major, bool)
        or config.contract_major != CONTRACT_MAJOR
    ):
        raise RuntimeConfigError(f"services.codex_broker.contract_major must be {CONTRACT_MAJOR}")
    if (
        not isinstance(config.contract_minor, int)
        or isinstance(config.contract_minor, bool)
        or config.contract_minor < 0
    ):
        raise RuntimeConfigError(
            "services.codex_broker.contract_minor must be a non-negative integer"
        )
    if (
        not isinstance(config.credential_role, str)
        or config.credential_role not in CLIENT_CREDENTIAL_ROLES
    ):
        allowed = ", ".join(sorted(CLIENT_CREDENTIAL_ROLES))
        raise RuntimeConfigError(
            f"services.codex_broker.credential_role must be one of: {allowed}"
        )


def _require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeConfigError(f"{label} must be a JSON object")
    return value


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) == expected:
        return
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    details = []
    if missing:
        details.append(f"missing fields: {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected fields: {', '.join(unexpected)}")
    raise RuntimeConfigError(f"{label} has invalid fields ({'; '.join(details)})")


def _require_string(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise RuntimeConfigError(f"{label} must be a non-empty, single-line string")
    return value


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for field, value in pairs:
        if field in decoded:
            raise RuntimeConfigError(f"broker runtime configuration repeats field: {field}")
        decoded[field] = value
    return decoded
