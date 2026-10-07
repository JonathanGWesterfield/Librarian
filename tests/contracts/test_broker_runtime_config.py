"""Tests for the sanitized per-client broker configuration contract."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.runtime_config import (
    BROKER_TRANSPORT,
    CLIENT_CREDENTIAL_ROLES,
    DOCKER_BROKER_TARGET,
    RuntimeConfigError,
    build_broker_client_runtime_config,
    load_broker_client_runtime_config,
    parse_broker_client_runtime_config,
    serialize_broker_client_runtime_config,
)


class BrokerRuntimeConfigTests(unittest.TestCase):
    """Runtime files must be minimal, reproducible, and unable to name a secret."""

    def test_builder_matches_the_tracked_non_secret_fixture(self) -> None:
        config = build_broker_client_runtime_config(
            model="gpt-5.6-sol",
            answer_capability="quality",
            credential_role="api",
            contract_minor=3,
        )

        expected = (REPO_ROOT / "tests/fixtures/answer_delivery/v1/broker_runtime_config.json").read_text(
            encoding="utf-8"
        )
        rendered = serialize_broker_client_runtime_config(config)

        self.assertEqual(rendered, expected)
        self.assertNotIn("api_key_file", rendered)
        self.assertNotIn("/run/secrets", rendered)
        self.assertNotIn("bridge-token", rendered)
        self.assertEqual(parse_broker_client_runtime_config(rendered), config)

    def test_each_supported_client_has_a_distinct_logical_credential_role(self) -> None:
        for role in CLIENT_CREDENTIAL_ROLES:
            with self.subTest(role=role):
                config = build_broker_client_runtime_config(
                    model="gpt-5.6-sol",
                    answer_capability="quality",
                    credential_role=role,
                )
                parsed = json.loads(serialize_broker_client_runtime_config(config))

                self.assertEqual(
                    parsed["services"]["codex_broker"],
                    {
                        "transport": BROKER_TRANSPORT,
                        "target": DOCKER_BROKER_TARGET,
                        "contract_major": 1,
                        "contract_minor": 0,
                        "credential_role": role,
                    },
                )

    def test_parser_rejects_hidden_credentials_paths_roles_and_targets(self) -> None:
        valid = {
            "version": 1,
            "generation": {"model": "gpt-5.6-sol", "answer_capability": "quality"},
            "services": {
                "codex_broker": {
                    "transport": "grpc",
                    "target": DOCKER_BROKER_TARGET,
                    "contract_major": 1,
                    "contract_minor": 0,
                    "credential_role": "api",
                }
            },
        }
        cases = {
            "top-level credential": {**valid, "api_key_file": "secrets/api.token"},
            "generation credential": {
                **valid,
                "generation": {**valid["generation"], "api_key_file": "secrets/api.token"},
            },
            "broker secret path": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "credential_file": "/run/secrets/codex-broker-api",
                    }
                },
            },
            "untrusted target": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "target": "dns:///another-broker:50051",
                    }
                },
            },
            "HTTP target": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "target": "http://codex-broker:3000/v1",
                    }
                },
            },
            "unknown role": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "credential_role": "compose-health",
                    }
                },
            },
            "wrong major": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "contract_major": 2,
                    }
                },
            },
            "bad minor": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "contract_minor": True,
                    }
                },
            },
            "boolean version": {**valid, "version": True},
            "non-canonical model": {
                **valid,
                "generation": {**valid["generation"], "model": " gpt-5.6-sol "},
            },
            "non-string capability": {
                **valid,
                "generation": {**valid["generation"], "answer_capability": ["quality"]},
            },
            "non-string role": {
                **valid,
                "services": {
                    "codex_broker": {
                        **valid["services"]["codex_broker"],
                        "credential_role": {"role": "api"},
                    }
                },
            },
        }

        for description, payload in cases.items():
            with self.subTest(description=description), self.assertRaises(RuntimeConfigError):
                parse_broker_client_runtime_config(json.dumps(payload))

        repeated_role = (
            '{"version":1,"generation":{"model":"gpt-5.6-sol",'
            '"answer_capability":"quality"},"services":{"codex_broker":'
            '{"transport":"grpc","target":"dns:///codex-broker:50051",'
            '"contract_major":1,"contract_minor":0,"credential_role":"api",'
            '"credential_role":"evaluator"}}}'
        )
        with self.assertRaisesRegex(RuntimeConfigError, "repeats field"):
            parse_broker_client_runtime_config(repeated_role)

    def test_loader_uses_the_same_strict_parser(self) -> None:
        config = build_broker_client_runtime_config(
            model="gpt-5.6-sol",
            answer_capability="quality",
            credential_role="evaluator",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "librarian.json"
            path.write_text(serialize_broker_client_runtime_config(config), encoding="utf-8")
            self.assertEqual(load_broker_client_runtime_config(path), config)

    def test_loader_refuses_symlinked_or_non_regular_configuration_files(self) -> None:
        config = build_broker_client_runtime_config(
            model="gpt-5.6-sol",
            answer_capability="quality",
            credential_role="api",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "actual-librarian.json"
            target.write_text(serialize_broker_client_runtime_config(config), encoding="utf-8")
            symlink = root / "librarian.json"
            symlink.symlink_to(target)

            with self.assertRaisesRegex(RuntimeConfigError, "could not read"):
                load_broker_client_runtime_config(symlink)

            with self.assertRaisesRegex(RuntimeConfigError, "could not read"):
                load_broker_client_runtime_config(root)


if __name__ == "__main__":
    unittest.main()
