"""Live R2 caller isolation and compatibility probe for the Compose harness."""

from __future__ import annotations

import asyncio
import socket
import sys

import grpc
from grpc_status import rpc_status
from librarian_answer_adapters.r2_startup import open_r2_client
from librarian_contracts.capabilities import build_capabilities_request
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)


async def _run(*, principal: str, alternate_broker_ip: str) -> None:
    client = await open_r2_client(expected_principal=principal)
    try:
        _assert_alternate_network_is_unreachable(alternate_broker_ip)
        for mutate in (
            lambda request: setattr(request, "stack_release_sha", "b" * 40),
            lambda request: setattr(request, "descriptor_sha256", b"x" * 32),
            lambda request: setattr(request, "contract_minor", request.contract_minor + 1),
            lambda request: setattr(request, "contract_major", request.contract_major + 1),
        ):
            request = build_capabilities_request(client.contract)
            mutate(request)
            await _assert_contract_mismatch(client, request)
    finally:
        await client.close()


def _assert_alternate_network_is_unreachable(address: str) -> None:
    try:
        with socket.create_connection((address, 50051), timeout=0.2):
            raise RuntimeError("caller reached the broker through another private network")
    except OSError:
        return


async def _assert_contract_mismatch(client, request) -> None:
    try:
        await client._stub.GetCapabilities(
            request,
            metadata=client._metadata(request_id="00000000-0000-4000-8000-000000000000"),
            timeout=2,
        )
    except grpc.aio.AioRpcError as error:
        if error.code() != grpc.StatusCode.FAILED_PRECONDITION:
            raise RuntimeError("caller mismatch did not fail with FAILED_PRECONDITION") from error
        if _error_code(error) != delivery_pb2.CONTRACT_MISMATCH:
            raise RuntimeError("caller mismatch did not return CONTRACT_MISMATCH") from error
    else:
        raise RuntimeError("caller mismatch unexpectedly completed the capability handshake")


def _error_code(error: grpc.aio.AioRpcError) -> int | None:
    status = rpc_status.from_call(error)
    if status is None:
        return None
    for packed in status.details:
        detail = delivery_pb2.ErrorDetail()
        if packed.Is(detail.DESCRIPTOR):
            packed.Unpack(detail)
            return detail.code
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("usage: caller_isolation_probe.py <principal> <alternate-broker-ip>")
    asyncio.run(_run(principal=argv[1], alternate_broker_ip=argv[2]))
    print(f"[librarian] R2 caller isolation probe passed for {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
