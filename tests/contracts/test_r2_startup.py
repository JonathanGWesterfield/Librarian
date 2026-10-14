"""Tests for the R2 caller preflight and authenticated startup handshake."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer_adapters.r2_startup import (
    R2StartupError,
    verify_r2_client_startup,
)
from librarian_contracts.broker_client_admission import BrokerClientAdmission
from librarian_contracts.broker_client_preflight import BrokerClientPreflight
from librarian_contracts.runtime_config import build_broker_client_runtime_config
from librarian_contracts.stack_contract import build_stack_contract


class R2StartupTests(unittest.IsolatedAsyncioTestCase):
    """A caller is not allowed to launch until its handshake is successful."""

    async def test_preflight_manifest_and_capability_handshake_complete_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "codex-broker-api"
            secret.write_text("api-token\n", encoding="utf-8")
            descriptor = Path(directory) / "answer_delivery.pb"
            descriptor.write_bytes(b"fixture descriptor")
            preflight = BrokerClientPreflight(
                runtime_config=build_broker_client_runtime_config(
                    model="gpt-5.6-sol",
                    answer_capability="quality",
                    credential_role="api",
                ),
                admission=BrokerClientAdmission(principal="api", credential_file=secret),
            )
            client = _Client()
            contract = build_stack_contract(
                stack_release_sha="a" * 40,
                descriptor=b"fixture descriptor",
            )
            with (
                patch("librarian_answer_adapters.r2_startup.preflight_broker_client", return_value=preflight),
                patch("librarian_answer_adapters.r2_startup.load_stack_contract", return_value=contract),
                patch("librarian_answer_adapters.r2_startup.PROTO_DESCRIPTOR_PATH", descriptor),
                patch(
                    "librarian_answer_adapters.r2_startup.GeneratedGrpcBrokerClient.connect",
                    return_value=client,
                ) as connect,
            ):
                await verify_r2_client_startup(expected_principal="api")

        self.assertTrue(client.ensure_ready_called)
        self.assertTrue(client.close_called)
        self.assertEqual(connect.call_args.kwargs["principal"], "api")
        self.assertEqual(connect.call_args.kwargs["bearer_token"], "api-token")

    async def test_role_mismatch_stops_before_manifest_or_channel_construction(self) -> None:
        preflight = BrokerClientPreflight(
            runtime_config=build_broker_client_runtime_config(
                model="gpt-5.6-sol",
                answer_capability="quality",
                credential_role="api",
            ),
            admission=BrokerClientAdmission(principal="api", credential_file=Path("/unused")),
        )
        with (
            patch("librarian_answer_adapters.r2_startup.preflight_broker_client", return_value=preflight),
            patch(
                "librarian_answer_adapters.r2_startup.load_stack_contract",
                side_effect=AssertionError("must not load a contract"),
            ) as load_contract,
            self.assertRaisesRegex(R2StartupError, "does not match"),
        ):
            await verify_r2_client_startup(expected_principal="evaluator")
        load_contract.assert_not_called()

    async def test_runtime_contract_mismatch_stops_before_credential_or_channel_construction(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            descriptor = Path(directory) / "answer_delivery.pb"
            descriptor.write_bytes(b"fixture descriptor")
            preflight = BrokerClientPreflight(
                runtime_config=build_broker_client_runtime_config(
                    model="gpt-5.6-sol",
                    answer_capability="quality",
                    credential_role="api",
                    contract_minor=1,
                ),
                admission=BrokerClientAdmission(
                    principal="api",
                    credential_file=Path(directory) / "must-not-read",
                ),
            )
            contract = build_stack_contract(
                stack_release_sha="a" * 40,
                descriptor=b"fixture descriptor",
            )
            with (
                patch(
                    "librarian_answer_adapters.r2_startup.preflight_broker_client",
                    return_value=preflight,
                ),
                patch("librarian_answer_adapters.r2_startup.load_stack_contract", return_value=contract),
                patch("librarian_answer_adapters.r2_startup.PROTO_DESCRIPTOR_PATH", descriptor),
                patch(
                    "librarian_answer_adapters.r2_startup.GeneratedGrpcBrokerClient.connect",
                    side_effect=AssertionError("must not construct a channel"),
                ) as connect,
                self.assertRaisesRegex(R2StartupError, "does not match the immutable"),
            ):
                await verify_r2_client_startup(expected_principal="api")

        connect.assert_not_called()

    async def test_handshake_failure_closes_the_channel_and_stops_startup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "codex-broker-api"
            secret.write_text("api-token\n", encoding="utf-8")
            descriptor = Path(directory) / "answer_delivery.pb"
            descriptor.write_bytes(b"fixture descriptor")
            preflight = BrokerClientPreflight(
                runtime_config=build_broker_client_runtime_config(
                    model="gpt-5.6-sol",
                    answer_capability="quality",
                    credential_role="api",
                ),
                admission=BrokerClientAdmission(principal="api", credential_file=secret),
            )
            client = _Client(fail_handshake=True)
            contract = build_stack_contract(
                stack_release_sha="a" * 40,
                descriptor=b"fixture descriptor",
            )
            with (
                patch("librarian_answer_adapters.r2_startup.preflight_broker_client", return_value=preflight),
                patch("librarian_answer_adapters.r2_startup.load_stack_contract", return_value=contract),
                patch("librarian_answer_adapters.r2_startup.PROTO_DESCRIPTOR_PATH", descriptor),
                patch(
                    "librarian_answer_adapters.r2_startup.GeneratedGrpcBrokerClient.connect",
                    return_value=client,
                ),
                self.assertRaisesRegex(R2StartupError, "capability handshake failed"),
            ):
                await verify_r2_client_startup(expected_principal="api")

        self.assertTrue(client.close_called)


class _Client:
    def __init__(self, *, fail_handshake: bool = False) -> None:
        self.fail_handshake = fail_handshake
        self.ensure_ready_called = False
        self.close_called = False

    async def ensure_ready(self, *, timeout: float | None = None) -> None:
        self.ensure_ready_called = True
        if self.fail_handshake:
            import grpc
            from librarian_answer_adapters.grpc_broker import GrpcBrokerClientError

            raise GrpcBrokerClientError(status=grpc.StatusCode.UNAVAILABLE, error_code=None)

    async def close(self) -> None:
        self.close_called = True


if __name__ == "__main__":
    unittest.main()
