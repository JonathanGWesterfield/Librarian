"""Executable R2 Compose isolation policy for the future gRPC broker rollout.

The current R0 Compose file intentionally does not satisfy this policy.  M03
will render its atomic R2 topology and call this validator before live tests;
M01 keeps the security boundary reviewable and deterministic in the meantime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from librarian_contracts.runtime_config import CLIENT_CREDENTIAL_ROLES

BROKER_SERVICE = "codex-broker"
BROKER_HEALTH_ROLE = "compose-health"
APPLICATION_NETWORK = "application"
BROKER_EGRESS_NETWORK = "broker-egress"
BROKER_PRIVATE_NETWORKS = {
    "api": "broker-api",
    "summary-worker": "broker-summary-worker",
    "metadata-worker": "broker-metadata-worker",
    "evaluator": "broker-evaluator",
}
BROKER_SECRET_NAMES = {
    role: f"codex-broker-{role}"
    for role in (*sorted(CLIENT_CREDENTIAL_ROLES), BROKER_HEALTH_ROLE)
}
RUNTIME_CONFIG_TARGET = "/config/librarian.json"
BROKER_GRPC_PORT = "50051"
WEB_SERVICE = "web"


class ComposeSecurityPolicyError(ValueError):
    """A rendered R2 Compose topology widens a broker security boundary."""


def validate_r2_compose_security(compose: Mapping[str, Any]) -> None:
    """Require the exact per-role secret, network, and runtime-config policy.

    This accepts the normalized mapping shape emitted by ``docker compose
    config``.  It does not start containers or change R0 configuration.
    """

    root = _require_mapping(compose, "compose")
    services = _require_mapping(root.get("services"), "compose.services")
    networks = _require_mapping(root.get("networks"), "compose.networks")
    secrets = _require_mapping(root.get("secrets"), "compose.secrets")

    _validate_network_definitions(networks)
    _validate_secret_definitions(secrets)
    _validate_broker_service(_service(services, BROKER_SERVICE))
    for role in BROKER_PRIVATE_NETWORKS:
        _validate_client_service(_service(services, role), role, role)

    for service_name in (*BROKER_PRIVATE_NETWORKS, BROKER_SERVICE, WEB_SERVICE):
        _reject_recursive_config_mounts(_service(services, service_name), service_name)


def _validate_network_definitions(networks: Mapping[str, Any]) -> None:
    expected = {
        APPLICATION_NETWORK: False,
        BROKER_EGRESS_NETWORK: False,
        **{network: True for network in BROKER_PRIVATE_NETWORKS.values()},
    }
    for network_name, expected_internal in expected.items():
        network = _require_mapping(networks.get(network_name), f"networks.{network_name}")
        internal = network.get("internal", False)
        if internal is not expected_internal:
            raise ComposeSecurityPolicyError(
                f"networks.{network_name}.internal must be {str(expected_internal).lower()}"
            )


def _validate_secret_definitions(secrets: Mapping[str, Any]) -> None:
    for secret_name in BROKER_SECRET_NAMES.values():
        secret = _require_mapping(secrets.get(secret_name), f"secrets.{secret_name}")
        if not _is_expected_secret_source(secret.get("file"), secret_name):
            raise ComposeSecurityPolicyError(
                f"secrets.{secret_name}.file must name its role-specific ignored secret"
            )


def _validate_broker_service(service: Mapping[str, Any]) -> None:
    required_networks = set(BROKER_PRIVATE_NETWORKS.values()) | {BROKER_EGRESS_NETWORK}
    _require_exact_networks(service, BROKER_SERVICE, required_networks)
    if APPLICATION_NETWORK in _network_names(service, BROKER_SERVICE):
        raise ComposeSecurityPolicyError("codex-broker must not join the application network")
    if service.get("ports"):
        raise ComposeSecurityPolicyError("codex-broker must not publish a host port")
    exposed_ports = {
        str(port)
        for port in _require_sequence(service.get("expose"), "codex-broker.expose")
    }
    if exposed_ports != {BROKER_GRPC_PORT}:
        raise ComposeSecurityPolicyError("codex-broker must expose exactly its private gRPC port")
    _require_secret_mounts(
        service,
        BROKER_SERVICE,
        expected_roles=(*sorted(CLIENT_CREDENTIAL_ROLES), BROKER_HEALTH_ROLE),
    )
    _require_runtime_config_mount(service, BROKER_SERVICE)


def _validate_client_service(
    service: Mapping[str, Any], service_name: str, role: str
) -> None:
    _require_exact_networks(
        service,
        service_name,
        {APPLICATION_NETWORK, BROKER_PRIVATE_NETWORKS[role]},
    )
    _require_secret_mounts(service, service_name, expected_roles=(role,))
    _require_runtime_config_mount(service, service_name)
    environment = _require_mapping(service.get("environment"), f"{service_name}.environment")
    expected_secret_path = f"/run/secrets/{BROKER_SECRET_NAMES[role]}"
    if environment.get("LIBRARIAN_EXECUTION_PRINCIPAL") != role:
        raise ComposeSecurityPolicyError(
            f"{service_name} must declare its non-spoofable execution principal"
        )
    if environment.get("LIBRARIAN_BROKER_CREDENTIAL_FILE") != expected_secret_path:
        raise ComposeSecurityPolicyError(
            f"{service_name} must declare only its role-specific broker credential path"
        )


def _require_exact_networks(
    service: Mapping[str, Any], service_name: str, expected: set[str]
) -> None:
    actual = _network_names(service, service_name)
    if actual != expected:
        expected_names = ", ".join(sorted(expected))
        actual_names = ", ".join(sorted(actual))
        raise ComposeSecurityPolicyError(
            f"{service_name}.networks must be exactly [{expected_names}], got [{actual_names}]"
        )


def _network_names(service: Mapping[str, Any], service_name: str) -> set[str]:
    networks = service.get("networks")
    if isinstance(networks, Mapping) or (
        isinstance(networks, Sequence) and not isinstance(networks, (str, bytes))
    ):
        names = set(networks)
    else:
        raise ComposeSecurityPolicyError(f"{service_name}.networks must be a mapping or list")
    if not names or any(not isinstance(name, str) for name in names):
        raise ComposeSecurityPolicyError(f"{service_name}.networks must contain service-network names")
    return names


def _require_secret_mounts(
    service: Mapping[str, Any], service_name: str, *, expected_roles: Sequence[str]
) -> None:
    expected = {BROKER_SECRET_NAMES[role] for role in expected_roles}
    mounts = _require_sequence(service.get("secrets"), f"{service_name}.secrets")
    seen: set[str] = set()
    for index, raw_mount in enumerate(mounts):
        mount = _require_mapping(raw_mount, f"{service_name}.secrets[{index}]")
        source = mount.get("source")
        target = mount.get("target")
        mode = mount.get("mode")
        if (
            not isinstance(source, str)
            or source not in expected
            or target != source
            or not _is_read_only_secret_mode(mode)
        ):
            raise ComposeSecurityPolicyError(
                f"{service_name}.secrets must use one read-only, role-specific mount per secret"
            )
        seen.add(source)
    if seen != expected or len(mounts) != len(expected):
        raise ComposeSecurityPolicyError(
            f"{service_name}.secrets must mount exactly its permitted broker secrets"
        )


def _is_read_only_secret_mode(mode: object) -> bool:
    return mode in {0o400, "0400"}


def _require_runtime_config_mount(service: Mapping[str, Any], service_name: str) -> None:
    expected_source = f"./.runtime/config/{service_name}/librarian.json"
    expected_short = f"{expected_source}:{RUNTIME_CONFIG_TARGET}:ro"
    volumes = _require_sequence(service.get("volumes"), f"{service_name}.volumes")
    matches = 0
    for index, volume in enumerate(volumes):
        if volume == expected_short:
            matches += 1
            continue
        if isinstance(volume, Mapping):
            source = volume.get("source")
            if (
                _is_expected_runtime_config_source(source, service_name)
                and volume.get("target") == RUNTIME_CONFIG_TARGET
                and volume.get("read_only") is True
            ):
                matches += 1
                continue
        source, target = _mount_source_and_target(volume, f"{service_name}.volumes[{index}]")
        if _is_expected_runtime_config_source(source, service_name):
            raise ComposeSecurityPolicyError(
                f"{service_name} may mount its sanitized librarian.json only at its fixed target"
            )
        if _is_user_owned_config_source(source, service_name) or target == "/config" or target.startswith("/config/"):
            raise ComposeSecurityPolicyError(
                f"{service_name} may mount only its sanitized librarian.json below /config"
            )
    if matches != 1:
        raise ComposeSecurityPolicyError(
            f"{service_name} must mount exactly its sanitized runtime librarian.json"
        )


def _reject_recursive_config_mounts(service: Mapping[str, Any], service_name: str) -> None:
    volumes = service.get("volumes", [])
    if not isinstance(volumes, Sequence) or isinstance(volumes, (str, bytes)):
        raise ComposeSecurityPolicyError(f"{service_name}.volumes must be a list")
    for index, volume in enumerate(volumes):
        source, target = _mount_source_and_target(volume, f"{service_name}.volumes[{index}]")
        if _is_user_owned_config_source(source, service_name):
            raise ComposeSecurityPolicyError(f"{service_name} must not mount user-owned config or secrets")
        if target == "/config" or target == "/config/secrets" or target.startswith("/config/secrets/"):
            raise ComposeSecurityPolicyError(f"{service_name} must not expose a recursive config or secrets mount")


def _mount_source_and_target(volume: object, label: str) -> tuple[str, str]:
    if isinstance(volume, Mapping):
        source = volume.get("source")
        target = volume.get("target")
    elif isinstance(volume, str):
        parts = volume.split(":")
        if len(parts) < 2:
            raise ComposeSecurityPolicyError(f"{label} must name a source and target")
        source, target = parts[0], parts[1]
    else:
        raise ComposeSecurityPolicyError(f"{label} must be a mapping or short volume string")
    if not isinstance(source, str) or not isinstance(target, str):
        raise ComposeSecurityPolicyError(f"{label} must use string source and target values")
    return source, target


def _is_expected_secret_source(source: object, secret_name: str) -> bool:
    return isinstance(source, str) and _has_path_suffix(
        source, "config", "secrets", secret_name
    )


def _is_expected_runtime_config_source(source: object, service_name: str) -> bool:
    return isinstance(source, str) and _has_path_suffix(
        source, ".runtime", "config", service_name, "librarian.json"
    )


def _is_user_owned_config_source(source: str, service_name: str) -> bool:
    if _is_expected_runtime_config_source(source, service_name):
        return False
    return "config" in _path_parts(source)


def _has_path_suffix(source: str, *expected_suffix: str) -> bool:
    parts = _path_parts(source)
    return tuple(parts[-len(expected_suffix) :]) == expected_suffix


def _path_parts(source: str) -> tuple[str, ...]:
    return tuple(part for part in source.replace("\\", "/").split("/") if part and part != ".")


def _service(services: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return _require_mapping(services.get(name), f"services.{name}")


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ComposeSecurityPolicyError(f"{label} must be a mapping")
    return value


def _require_sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ComposeSecurityPolicyError(f"{label} must be a list")
    return value
