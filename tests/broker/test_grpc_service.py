"""Deterministic integration tests for the M03 gRPC broker control plane."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_status import rpc_status

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer_adapters.grpc_broker import GeneratedGrpcBrokerClient
from librarian_broker.execution import (
    BrokerScheduler,
    CodexSubprocessExecutor,
    ProviderExecutor,
)
from librarian_broker.grpc_service import (
    BrokerCredentials,
    create_broker_server,
)
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2_grpc as delivery_grpc,
)
from librarian_contracts.stack_contract import build_stack_contract


class GrpcBrokerServiceTests(unittest.IsolatedAsyncioTestCase):
    """The foundation authenticates Health and compatibility before execution."""

    async def asyncSetUp(self) -> None:
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"M03 fixture descriptor",
        )
        self.credentials = BrokerCredentials({
            "api": "api-token",
            "compose-health": "health-token",
        })
        await self._start_server(_FakeProvider())

    async def _start_server(self, provider: ProviderExecutor) -> None:
        self.provider = provider
        self.scheduler = BrokerScheduler(
            provider, limits=build_broker_execution_limits()
        )
        self.server = create_broker_server(
            contract=self.contract,
            credentials=self.credentials,
            scheduler=self.scheduler,
        )
        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()
        self.channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        self.stub = delivery_grpc.GenerationBrokerStub(self.channel)
        self.health = health_pb2_grpc.HealthStub(self.channel)

    async def _replace_provider(self, provider: ProviderExecutor) -> None:
        await self.channel.close()
        await self.server.stop(0)
        await self._start_server(provider)

    async def asyncTearDown(self) -> None:
        await self.channel.close()
        await self.server.stop(0)

    def _metadata(
        self,
        token: str,
        *,
        release: str | None = None,
        request_id: str = "10000000-0000-4000-8000-000000000001",
    ):
        return (
            ("authorization", f"Bearer {token}"),
            ("x-librarian-request-id", request_id),
            ("x-librarian-stack-release", release or self.contract.stack_release_sha),
        )

    def _request(self, **overrides) -> delivery_pb2.CapabilitiesRequest:
        payload = {
            "contract_major": self.contract.contract_major,
            "contract_minor": self.contract.contract_minor,
            "descriptor_sha256": bytes.fromhex(self.contract.descriptor_sha256),
            "stack_release_sha": self.contract.stack_release_sha,
        }
        payload.update(overrides)
        return delivery_pb2.CapabilitiesRequest(**payload)

    def _generate_request(self, **overrides) -> delivery_pb2.GenerateRequest:
        payload = {
            "request_id": "10000000-0000-4000-8000-000000000001",
            "correlation_id": "grpc-service-test",
            "operation": delivery_pb2.CHAPTER_SUMMARIZATION,
            "model_id": "gpt-5.6-sol",
            "messages": [
                delivery_pb2.ChatMessage(role=delivery_pb2.USER, content="Summarize.")
            ],
            "output_contract": delivery_pb2.PLAIN_TEXT_V1,
        }
        payload.update(overrides)
        return delivery_pb2.GenerateRequest(**payload)

    async def test_authenticated_capabilities_returns_the_immutable_manifest(self) -> None:
        response = await self.stub.GetCapabilities(
            self._request(), metadata=self._metadata("api-token")
        )

        self.assertEqual(response.contract_major, self.contract.contract_major)
        self.assertEqual(response.min_contract_minor, self.contract.contract_minor)
        self.assertEqual(response.max_contract_minor, self.contract.contract_minor)
        self.assertEqual(response.descriptor_sha256.hex(), self.contract.descriptor_sha256)
        self.assertEqual(response.stack_release_sha, self.contract.stack_release_sha)
        self.assertEqual(set(response.operations), set(range(1, 10)))

    async def test_aio_generated_client_completes_the_capability_handshake(self) -> None:
        client = GeneratedGrpcBrokerClient(
            channel=self.channel,
            contract=self.contract,
            principal="api",
            bearer_token="api-token",
        )

        await client.ensure_ready()

    async def test_authentication_and_manifest_mismatch_use_typed_status_details(self) -> None:
        cases = (
            (
                "missing credential",
                (),
                self._request(),
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
            ),
            (
                "metadata release mismatch",
                self._metadata("api-token", release="b" * 40),
                self._request(),
                grpc.StatusCode.FAILED_PRECONDITION,
                delivery_pb2.CONTRACT_MISMATCH,
            ),
            (
                "descriptor mismatch",
                self._metadata("api-token"),
                self._request(descriptor_sha256=b"x" * 32),
                grpc.StatusCode.FAILED_PRECONDITION,
                delivery_pb2.CONTRACT_MISMATCH,
            ),
            (
                "invalid request metadata",
                self._metadata("api-token", request_id="not-a-uuid"),
                self._request(),
                grpc.StatusCode.INVALID_ARGUMENT,
                delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            ),
        )
        for name, metadata, request, expected_status, expected_code in cases:
            with self.subTest(name=name):
                with self.assertRaises(grpc.aio.AioRpcError) as raised:
                    await self.stub.GetCapabilities(request, metadata=metadata)
                error = raised.exception
                self.assertEqual(error.code(), expected_status)
                status = rpc_status.from_call(error)
                self.assertIsNotNone(status)
                assert status is not None
                self.assertEqual(len(status.details), 1)
                detail = delivery_pb2.ErrorDetail()
                self.assertTrue(status.details[0].Unpack(detail))
                self.assertEqual(detail.code, expected_code)

    async def test_health_requires_the_dedicated_health_credential(self) -> None:
        response = await self.health.Check(
            health_pb2.HealthCheckRequest(),
            metadata=self._metadata("health-token"),
        )
        self.assertEqual(response.status, health_pb2.HealthCheckResponse.SERVING)

        with self.assertRaises(grpc.aio.AioRpcError) as raised:
            await self.health.Check(
                health_pb2.HealthCheckRequest(),
                metadata=self._metadata("api-token"),
            )
        self.assertEqual(raised.exception.code(), grpc.StatusCode.UNAUTHENTICATED)

    async def test_generate_validates_and_authorizes_before_scheduler_admission(self) -> None:
        result = await self.stub.Generate(
            self._generate_request(), metadata=self._metadata("api-token")
        )
        self.assertEqual(result.success.content, "Fixture provider output.")
        self.assertEqual(result.provider_model_id, "fixture-model")
        self.assertEqual(self.provider.calls, 1)

        invalid = self._generate_request(correlation_id="")
        denied = self._generate_request(
            operation=delivery_pb2.TAG_GENERATION,
            output_contract=delivery_pb2.TAGS_JSON_V1,
            correlation_id="",
        )
        mismatched_metadata = self._generate_request()
        for request, expected_status, expected_code in (
            (
                invalid,
                grpc.StatusCode.INVALID_ARGUMENT,
                delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            ),
            (
                denied,
                grpc.StatusCode.PERMISSION_DENIED,
                delivery_pb2.OPERATION_DENIED,
            ),
        ):
            with self.subTest(request=request.operation):
                with self.assertRaises(grpc.aio.AioRpcError) as raised:
                    await self.stub.Generate(
                        request, metadata=self._metadata("api-token")
                    )
                self.assertEqual(raised.exception.code(), expected_status)
                status = rpc_status.from_call(raised.exception)
                assert status is not None
                detail = delivery_pb2.ErrorDetail()
                self.assertTrue(status.details[0].Unpack(detail))
                self.assertEqual(detail.code, expected_code)
        with self.assertRaises(grpc.aio.AioRpcError) as raised:
            await self.stub.Generate(
                mismatched_metadata,
                metadata=self._metadata(
                    "api-token",
                    request_id="10000000-0000-4000-8000-000000000099",
                ),
            )
        self.assertEqual(raised.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(self.provider.calls, 1)

    async def test_metadata_gate_rejects_unauthorized_and_unexpected_calls_pre_admission(self) -> None:
        request = self._generate_request(correlation_id="")
        cases = (
            ("missing credential", (), grpc.StatusCode.UNAUTHENTICATED, delivery_pb2.CALLER_DENIED),
            (
                "unexpected application metadata",
                self._metadata("api-token") + (("x-librarian-principal", "api"),),
                grpc.StatusCode.INVALID_ARGUMENT,
                delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            ),
            (
                "missing release metadata",
                (
                    ("authorization", "Bearer api-token"),
                    ("x-librarian-request-id", "10000000-0000-4000-8000-000000000001"),
                ),
                grpc.StatusCode.INVALID_ARGUMENT,
                delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            ),
        )
        for name, metadata, expected_status, expected_code in cases:
            with self.subTest(name=name):
                with self.assertRaises(grpc.aio.AioRpcError) as raised:
                    await self.stub.Generate(request, metadata=metadata)
                self.assertEqual(raised.exception.code(), expected_status)
                status = rpc_status.from_call(raised.exception)
                assert status is not None
                detail = delivery_pb2.ErrorDetail()
                self.assertTrue(status.details[0].Unpack(detail))
                self.assertEqual(detail.code, expected_code)
        self.assertEqual(self.provider.calls, 0)

    async def test_transport_rejects_an_oversized_request_before_provider_admission(self) -> None:
        oversized = self._generate_request(
            messages=[
                delivery_pb2.ChatMessage(
                    role=delivery_pb2.USER, content="x" * (513 * 1024)
                )
            ]
        )

        with self.assertRaises(grpc.aio.AioRpcError) as raised:
            await self.stub.Generate(oversized, metadata=self._metadata("api-token"))

        self.assertEqual(raised.exception.code(), grpc.StatusCode.RESOURCE_EXHAUSTED)
        self.assertEqual(self.provider.calls, 0)

    async def test_rpc_cancellation_reaps_provider_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "provider-pids"
            script = (
                "import os, subprocess, sys, time\n"
                "from pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                f"Path({str(pid_path)!r}).write_text(f'{{os.getpid()}} {{child.pid}}')\n"
                "time.sleep(60)\n"
            )
            await self._replace_provider(
                CodexSubprocessExecutor(
                    lambda _: [sys.executable, "-c", script]
                )
            )
            call = self.stub.Generate(
                self._generate_request(), metadata=self._metadata("api-token")
            )
            parent_pid, child_pid = await _read_process_ids(pid_path)
            call.cancel()
            try:
                await call
            except (asyncio.CancelledError, grpc.aio.AioRpcError):
                pass
            else:
                self.fail("cancelled RPC unexpectedly produced a response")
            try:
                await _wait_until_gone(parent_pid, child_pid)
            finally:
                _kill_if_alive(parent_pid)
                _kill_if_alive(child_pid)


class _FakeProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request, *, timeout_seconds):
        self.calls += 1
        return "Fixture provider output.", "fixture-model"


async def _read_process_ids(path: Path) -> tuple[int, int]:
    for _ in range(100):
        if path.exists():
            parent, child = path.read_text(encoding="utf-8").split()
            return int(parent), int(child)
        await asyncio.sleep(0.01)
    raise AssertionError("provider did not publish its process IDs")


async def _wait_until_gone(*process_ids: int) -> None:
    for _ in range(300):
        if all(not _process_exists(process_id) for process_id in process_ids):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"provider process group remained alive: {process_ids}")


def _process_exists(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    return True


def _kill_if_alive(process_id: int) -> None:
    if _process_exists(process_id):
        try:
            os.kill(process_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
