"""Tests for the R2 Compose secret, network, and config-mount policy."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.compose_security import (
    BROKER_SECRET_NAMES,
    ComposeSecurityPolicyError,
    validate_r2_compose_security,
)


class ComposeSecurityPolicyTests(unittest.TestCase):
    """M03 must not be able to widen any documented broker boundary."""

    def test_canonical_r2_shape_is_accepted(self) -> None:
        validate_r2_compose_security(_r2_compose())

    def test_accepts_docker_compose_normalized_sources(self) -> None:
        normalized = _r2_compose()
        for secret_name, definition in normalized["secrets"].items():
            definition["file"] = f"/workspace/config/secrets/{secret_name}"
        for service in normalized["services"].values():
            service["volumes"] = [_normalized_volume(volume) for volume in service.get("volumes", [])]
        validate_r2_compose_security(normalized)

    def test_rejects_broker_host_ports_and_widened_networks(self) -> None:
        host_port = _r2_compose()
        host_port["services"]["codex-broker"]["ports"] = ["50051:50051"]
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "host port"):
            validate_r2_compose_security(host_port)

        application_network = _r2_compose()
        application_network["services"]["codex-broker"]["networks"].append("application")
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "codex-broker.networks"):
            validate_r2_compose_security(application_network)

        cross_role_network = _r2_compose()
        cross_role_network["services"]["evaluator"]["networks"].append("broker-api")
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "evaluator.networks"):
            validate_r2_compose_security(cross_role_network)

        extra_exposed_port = _r2_compose()
        extra_exposed_port["services"]["codex-broker"]["expose"].append("8080")
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "expose exactly"):
            validate_r2_compose_security(extra_exposed_port)

    def test_rejects_another_roles_secret_or_non_read_only_mount(self) -> None:
        wrong_secret = _r2_compose()
        wrong_secret["services"]["api"]["secrets"][0]["source"] = BROKER_SECRET_NAMES["evaluator"]
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "role-specific"):
            validate_r2_compose_security(wrong_secret)

        writable_secret = _r2_compose()
        writable_secret["services"]["api"]["secrets"][0]["mode"] = "0644"
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "read-only"):
            validate_r2_compose_security(writable_secret)

    def test_rejects_recursive_config_and_missing_role_environment(self) -> None:
        recursive_config = _r2_compose()
        recursive_config["services"]["api"]["volumes"].append("./config:/config:ro")
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "sanitized librarian.json"):
            validate_r2_compose_security(recursive_config)

        absolute_recursive_config = _r2_compose()
        absolute_recursive_config["services"]["api"]["volumes"].append(
            "/workspace/config:/private-config:ro"
        )
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "sanitized librarian.json"):
            validate_r2_compose_security(absolute_recursive_config)

        missing_principal = _r2_compose()
        del missing_principal["services"]["api"]["environment"]["LIBRARIAN_EXECUTION_PRINCIPAL"]
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "execution principal"):
            validate_r2_compose_security(missing_principal)

    def test_rejects_missing_required_topology_member(self) -> None:
        missing_worker = _r2_compose()
        del missing_worker["services"]["metadata-worker"]
        with self.assertRaisesRegex(ComposeSecurityPolicyError, "metadata-worker"):
            validate_r2_compose_security(missing_worker)


def _r2_compose() -> dict[str, object]:
    compose = {
        "networks": {
            "application": {},
            "broker-api": {"internal": True},
            "broker-summary-worker": {"internal": True},
            "broker-metadata-worker": {"internal": True},
            "broker-evaluator": {"internal": True},
            "broker-egress": {},
        },
        "secrets": {
            name: {"file": f"./config/secrets/{name}"}
            for name in BROKER_SECRET_NAMES.values()
        },
        "services": {
            "codex-broker": {
                "networks": [
                    "broker-api",
                    "broker-summary-worker",
                    "broker-metadata-worker",
                    "broker-evaluator",
                    "broker-egress",
                ],
                "expose": ["50051"],
                "secrets": [_secret_mount(role) for role in (*_roles(), "compose-health")],
                "volumes": [
                    "./.runtime/config/codex-broker/librarian.json:/config/librarian.json:ro"
                ],
            },
            **{
                service: {
                    "networks": ["application", network],
                    "secrets": [_secret_mount(role)],
                    "volumes": [
                        f"./.runtime/config/{service}/librarian.json:/config/librarian.json:ro"
                    ],
                    "environment": {
                        "LIBRARIAN_EXECUTION_PRINCIPAL": role,
                        "LIBRARIAN_BROKER_CREDENTIAL_FILE": f"/run/secrets/{BROKER_SECRET_NAMES[role]}",
                    },
                }
                for service, role, network in (
                    ("api", "api", "broker-api"),
                    ("summary-worker", "summary-worker", "broker-summary-worker"),
                    ("metadata-worker", "metadata-worker", "broker-metadata-worker"),
                    ("evaluator", "evaluator", "broker-evaluator"),
                )
            },
            "web": {
                "networks": ["application"],
                "volumes": [],
            },
        },
    }
    return copy.deepcopy(compose)


def _roles() -> tuple[str, ...]:
    return ("api", "summary-worker", "metadata-worker", "evaluator")


def _secret_mount(role: str) -> dict[str, object]:
    secret = BROKER_SECRET_NAMES[role]
    return {"source": secret, "target": secret, "mode": "0400"}


def _normalized_volume(volume: str) -> dict[str, object]:
    source, target, mode = volume.split(":")
    return {
        "type": "bind",
        "source": f"/workspace/{source.removeprefix('./')}",
        "target": target,
        "read_only": mode == "ro",
    }


if __name__ == "__main__":
    unittest.main()
