"""Startup tests for the gRPC-only R2 broker process."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_broker import r2_main
from librarian_broker.execution import BrokerExecutionFailed
from librarian_contracts.broker_server_config import (
    build_broker_server_runtime_config,
    serialize_broker_server_runtime_config,
)
from librarian_contracts.compose_security import BROKER_SECRET_NAMES
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import (
    build_stack_contract,
    serialize_stack_contract,
)


class R2BrokerStartupTests(unittest.TestCase):
    """The R2 listener starts only from exact config, secrets, and manifest."""

    def test_main_reaches_grpc_start_with_strict_runtime_config(self) -> None:
        """R2 startup must not parse its strict config as legacy app settings."""

        server = _ServerThatReachedStartup()
        with _r2_broker_files() as files, _patch_paths(files), patch.object(
            r2_main, "create_broker_server", return_value=server
        ), self.assertRaises(_ReachedGrpcServerStart):
            r2_main.main()

        self.assertEqual(server.listen_address, r2_main.GRPC_LISTEN_ADDRESS)

    def test_loads_all_role_credentials_and_immutable_manifest(self) -> None:
        with _r2_broker_files() as files, _patch_paths(files):
            config, credentials, contract = r2_main.load_r2_broker_inputs()

        self.assertEqual(config.model, "gpt-5.6-sol")
        self.assertEqual(credentials.tokens_by_principal["api"], "api-token")
        self.assertEqual(
            credentials.tokens_by_principal["compose-health"], "compose-health-token"
        )
        self.assertEqual(contract.stack_release_sha, "a" * 40)

    def test_missing_role_credential_fails_without_disclosing_its_path(self) -> None:
        with _r2_broker_files() as files:
            (files.secrets / BROKER_SECRET_NAMES["evaluator"]).unlink()
            with _patch_paths(files), self.assertRaisesRegex(
                r2_main.BrokerStartupError, "credential material is unavailable"
            ):
                r2_main.load_r2_broker_inputs()

    def test_duplicate_role_credentials_are_rejected(self) -> None:
        with _r2_broker_files() as files:
            (files.secrets / BROKER_SECRET_NAMES["evaluator"]).write_text(
                "api-token\n", encoding="utf-8"
            )
            with _patch_paths(files), self.assertRaisesRegex(
                r2_main.BrokerStartupError, "credential material is invalid"
            ):
                r2_main.load_r2_broker_inputs()

    def test_provider_command_refuses_model_substitution(self) -> None:
        config = build_broker_server_runtime_config(
            model="gpt-5.6-sol", answer_capability="quality"
        )
        command = r2_main._codex_command_factory(config)

        with self.assertRaises(BrokerExecutionFailed):
            command(delivery_pb2.GenerateRequest(model_id="other-model"))

        self.assertEqual(
            command(delivery_pb2.GenerateRequest(model_id="gpt-5.6-sol"))[:4],
            ["codex", "exec", "--model", "gpt-5.6-sol"],
        )


class _r2_broker_files:
    def __enter__(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self._temporary_directory.name)
        self.config = root / "config" / "librarian.json"
        self.config.parent.mkdir()
        self.config.write_text(
            serialize_broker_server_runtime_config(
                build_broker_server_runtime_config(
                    model="gpt-5.6-sol", answer_capability="quality"
                )
            ),
            encoding="utf-8",
        )
        self.secrets = root / "secrets"
        self.secrets.mkdir()
        for role, secret_name in BROKER_SECRET_NAMES.items():
            path = self.secrets / secret_name
            path.write_text(f"{role}-token\n", encoding="utf-8")
            path.chmod(0o400)
        self.descriptor = root / "answer_delivery.pb"
        self.descriptor.write_bytes(b"fixture descriptor")
        self.manifest = root / "librarian-stack-contract.json"
        self.manifest.write_text(
            serialize_stack_contract(
                build_stack_contract(stack_release_sha="a" * 40, descriptor=self.descriptor.read_bytes())
            ),
            encoding="utf-8",
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._temporary_directory.cleanup()


def _patch_paths(files: _r2_broker_files):
    return patch.multiple(
        r2_main,
        BROKER_RUNTIME_CONFIG_PATH=files.config,
        BROKER_SECRETS_DIRECTORY=files.secrets,
        STACK_CONTRACT_PATH=files.manifest,
        PROTO_DESCRIPTOR_PATH=files.descriptor,
    )


class _ReachedGrpcServerStart(Exception):
    """Test sentinel proving strict config validation reached the gRPC server."""


class _ServerThatReachedStartup:
    def __init__(self) -> None:
        self.listen_address: str | None = None

    def add_insecure_port(self, address: str) -> int:
        self.listen_address = address
        return 1

    async def start(self) -> None:
        raise _ReachedGrpcServerStart


if __name__ == "__main__":
    unittest.main()
