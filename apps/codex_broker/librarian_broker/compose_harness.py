"""Run the deterministic R2 Compose broker used by acceptance verification.

This module is deliberately available only in the broker image.  The Compose
acceptance runner starts ``serve-fake`` instead of Codex so it can prove the
R2 transport, authorization, compatibility, and process-cleanup boundaries
without an account, private configuration, or source material.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_status import rpc_status
from librarian_contracts.admission import (
    OPERATION_POLICIES,
    is_operation_allowed,
    validate_generate_request,
)
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.capabilities import build_capabilities_request
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2_grpc as delivery_grpc,
)

from librarian_broker import r2_main
from librarian_broker.execution import (
    BrokerScheduler,
    CodexSubprocessExecutor,
    ProviderExecutor,
)
from librarian_broker.grpc_service import create_broker_server

_TARGET = "127.0.0.1:50051"
_REQUEST_ID_HEADER = "x-librarian-request-id"
_STACK_RELEASE_HEADER = "x-librarian-stack-release"
_CALLER_ROLES = ("api", "summary-worker", "metadata-worker", "evaluator")
_SLOW_MARKER = "__answer_delivery_compose_slow__"
_CANCELLATION_MARKER = "__answer_delivery_compose_cancel__"
_CANCELLATION_PID_PATH = Path("/tmp/librarian-answer-delivery-cancellation-pids")


class _FakeProvider(ProviderExecutor):
    """A tracked provider that cannot reach Codex or any external network."""

    async def generate(self, request, *, timeout_seconds: float) -> tuple[str, str]:
        if any(message.content == _CANCELLATION_MARKER for message in request.messages):
            return await _run_controlled_subprocess(request, timeout_seconds=timeout_seconds)
        del timeout_seconds
        if any(message.content == _SLOW_MARKER for message in request.messages):
            await asyncio.sleep(10)
        return "synthetic compose provider output", request.model_id


async def serve_fake() -> None:
    """Run the normal gRPC server with deterministic local provider work."""

    _config, credentials, contract = r2_main.load_r2_broker_inputs()
    server = create_broker_server(
        contract=contract,
        credentials=credentials,
        scheduler=BrokerScheduler(_FakeProvider(), limits=build_broker_execution_limits()),
    )
    if server.add_insecure_port(r2_main.GRPC_LISTEN_ADDRESS) == 0:
        raise r2_main.BrokerStartupError("R2 broker could not bind its private gRPC listener")

    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signal_name, stop_requested.set)
        except NotImplementedError:  # pragma: no cover - image runs on Linux
            pass
    await server.start()
    try:
        await stop_requested.wait()
    finally:
        await server.stop(r2_main.SHUTDOWN_DRAIN_SECONDS)


async def run_probes() -> dict[str, object]:
    """Run live, redacted assertions against the already-running fake broker."""

    config, credentials, contract = r2_main.load_r2_broker_inputs()
    health = await _probe_health(credentials.tokens_by_principal, contract, config.model)
    authorization = await _probe_authorization(
        credentials.tokens_by_principal, contract, config.model
    )
    compatibility = await _probe_compatibility(
        credentials.tokens_by_principal["api"], contract, config.model
    )
    cancellation = await _probe_cancellation()
    return {
        "compose_summary": {
            "schema_version": 1,
            "broker_health": health,
            "fake_provider": "synthetic",
            "http_listener": "absent",
        },
        "authorization": authorization,
        "compatibility": compatibility,
        "cancellation": cancellation,
    }


async def _probe_health(tokens: Mapping[str, str], contract, model: str) -> dict[str, object]:
    token_map = dict(tokens)
    channel = grpc.aio.insecure_channel(_TARGET)
    try:
        health_stub = health_pb2_grpc.HealthStub(channel)
        response = await health_stub.Check(
            health_pb2.HealthCheckRequest(),
            metadata=(("authorization", f"Bearer {token_map['compose-health']}"),),
            timeout=2,
        )
        if response.status != health_pb2.HealthCheckResponse.SERVING:
            raise RuntimeError("R2 broker health probe did not report SERVING")
        broker_stub = delivery_grpc.GenerationBrokerStub(channel)
        metadata = _metadata(token_map["compose-health"], contract.stack_release_sha)
        await broker_stub.GetCapabilities(
            build_capabilities_request(contract),
            metadata=metadata("00000000-0000-4000-8000-000000000000"),
            timeout=2,
        )
        request = _request_for(operation=delivery_pb2.CHAPTER_SUMMARIZATION, model=model)
        await _expect_rpc_status(
            broker_stub.Generate(request, metadata=metadata(request.request_id), timeout=2),
            grpc.StatusCode.PERMISSION_DENIED,
            error_code=delivery_pb2.OPERATION_DENIED,
        )
        await _expect_rpc_status(
            health_stub.Check(
                health_pb2.HealthCheckRequest(),
                metadata=(("authorization", f"Bearer {token_map['api']}"),),
                timeout=2,
            ),
            grpc.StatusCode.UNAUTHENTICATED,
            error_code=delivery_pb2.CALLER_DENIED,
        )
        return {
            "authenticated_health": "serving",
            "capabilities_verified": True,
            "generate_denied": True,
            "caller_health_denied": True,
        }
    finally:
        await channel.close()


async def _probe_authorization(
    tokens: Mapping[str, str], contract, model: str
) -> dict[str, object]:
    token_map = dict(tokens)
    authorized = 0
    denied = 0
    for principal in _CALLER_ROLES:
        channel = grpc.aio.insecure_channel(_TARGET)
        try:
            stub = delivery_grpc.GenerationBrokerStub(channel)
            metadata = _metadata(token_map[principal], contract.stack_release_sha)
            for operation in OPERATION_POLICIES:
                request = _request_for(operation=operation, model=model)
                if is_operation_allowed(principal=principal, operation=operation):
                    result = await stub.Generate(
                        request, metadata=metadata(request.request_id), timeout=3
                    )
                    if result.WhichOneof("outcome") != "success":
                        raise RuntimeError("authorized R2 operation did not return a synthetic result")
                    authorized += 1
                else:
                    await _expect_rpc_status(
                        stub.Generate(
                            request, metadata=metadata(request.request_id), timeout=3
                        ),
                        grpc.StatusCode.PERMISSION_DENIED,
                        error_code=delivery_pb2.OPERATION_DENIED,
                    )
                    denied += 1

            await _expect_rpc_status(
                stub.GetCapabilities(build_capabilities_request(contract), timeout=2),
                grpc.StatusCode.UNAUTHENTICATED,
                error_code=delivery_pb2.CALLER_DENIED,
            )
        finally:
            await channel.close()
    return {
        "schema_version": 1,
        "principals_checked": len(_CALLER_ROLES),
        "authorized_operations": authorized,
        "denied_operations": denied,
        "unauthenticated_denied": True,
    }


async def _probe_compatibility(token: str, contract, model: str) -> dict[str, object]:
    channel = grpc.aio.insecure_channel(_TARGET)
    try:
        stub = delivery_grpc.GenerationBrokerStub(channel)
        metadata = _metadata(token, contract.stack_release_sha)
        variants = {
            "release_sha": lambda request: setattr(
                request, "stack_release_sha", "b" * 40
            ),
            "descriptor": lambda request: setattr(
                request, "descriptor_sha256", b"x" * 32
            ),
            "minor": lambda request: setattr(
                request, "contract_minor", request.contract_minor + 1
            ),
            "major": lambda request: setattr(
                request, "contract_major", request.contract_major + 1
            ),
        }
        for mutate in variants.values():
            request = build_capabilities_request(contract)
            mutate(request)
            await _expect_rpc_status(
                stub.GetCapabilities(
                    request,
                    metadata=metadata("00000000-0000-4000-8000-000000000000"),
                    timeout=2,
                ),
                grpc.StatusCode.FAILED_PRECONDITION,
                error_code=delivery_pb2.CONTRACT_MISMATCH,
            )

        request = _request_for(
            operation=delivery_pb2.CHAPTER_SUMMARIZATION, model=model
        )
        await _expect_rpc_status(
            stub.Generate(
                request,
                metadata=_metadata(token, "b" * 40)(request.request_id),
                timeout=2,
            ),
            grpc.StatusCode.FAILED_PRECONDITION,
            error_code=delivery_pb2.CONTRACT_MISMATCH,
        )
        await _expect_unavailable(contract)
        await _expect_deadline(stub, metadata, model=model)
        await _expect_admission_full(stub, metadata, model=model)
        return {
            "schema_version": 1,
            "contract_mismatches": sorted(variants),
            "generate_release_mismatch_denied": True,
            "unhealthy_broker_denied": True,
            "deadline_denied": True,
            "queue_full_denied": True,
        }
    finally:
        await channel.close()


async def _expect_unavailable(contract) -> None:
    channel = grpc.aio.insecure_channel("127.0.0.1:1")
    try:
        stub = delivery_grpc.GenerationBrokerStub(channel)
        await _expect_rpc_status(
            stub.GetCapabilities(build_capabilities_request(contract), timeout=0.2),
            grpc.StatusCode.UNAVAILABLE,
        )
    finally:
        await channel.close()


async def _expect_deadline(stub, metadata, *, model: str) -> None:
    request = _request_for(
        operation=delivery_pb2.CHAPTER_SUMMARIZATION,
        model=model,
        content=_SLOW_MARKER,
    )
    await _expect_rpc_status(
        stub.Generate(request, metadata=metadata(request.request_id), timeout=0.05),
        grpc.StatusCode.DEADLINE_EXCEEDED,
        error_code=delivery_pb2.EXECUTION_TIMEOUT,
    )


async def _expect_admission_full(stub, metadata, *, model: str) -> None:
    active_request = _request_for(
        operation=delivery_pb2.CHAPTER_SUMMARIZATION,
        model=model,
        content=_SLOW_MARKER,
    )
    active = asyncio.ensure_future(
        stub.Generate(
            active_request, metadata=metadata(active_request.request_id), timeout=5
        )
    )
    try:
        await asyncio.sleep(0.1)
        queued_requests = [
            _request_for(
                operation=delivery_pb2.CHAPTER_SUMMARIZATION,
                model=model,
                content=_SLOW_MARKER,
            )
            for _ in range(5)
        ]
        queued = [
            stub.Generate(request, metadata=metadata(request.request_id), timeout=1.5)
            for request in queued_requests
        ]
        results = await asyncio.gather(*queued, return_exceptions=True)
        if not any(
            isinstance(result, grpc.aio.AioRpcError)
            and result.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
            and _error_code(result) == delivery_pb2.ADMISSION_FULL
            for result in results
        ):
            raise RuntimeError("R2 broker did not reject a full admission queue")
    finally:
        active.cancel()
        await asyncio.gather(active, return_exceptions=True)


async def _probe_cancellation() -> dict[str, object]:
    _CANCELLATION_PID_PATH.unlink(missing_ok=True)
    config, credentials, contract = r2_main.load_r2_broker_inputs()
    channel = grpc.aio.insecure_channel(_TARGET)
    try:
        stub = delivery_grpc.GenerationBrokerStub(channel)
        metadata = _metadata(credentials.tokens_by_principal["api"], contract.stack_release_sha)
        request = _request_for(
            operation=delivery_pb2.CHAPTER_SUMMARIZATION,
            model=config.model,
            content=_CANCELLATION_MARKER,
        )
        rpc = asyncio.ensure_future(
            stub.Generate(request, metadata=metadata(request.request_id), timeout=10)
        )
        parent_pid, child_pid = await _wait_for_cancellation_pids(_CANCELLATION_PID_PATH)
        rpc.cancel()
        try:
            await rpc
        except asyncio.CancelledError:
            pass
        else:  # pragma: no cover - defensive assertion for a broken transport
            raise RuntimeError("live Generate RPC did not propagate cancellation")
        await _wait_for_process_exit(parent_pid)
        await _wait_for_process_exit(child_pid)
    finally:
        _CANCELLATION_PID_PATH.unlink(missing_ok=True)
        await channel.close()
    return {"schema_version": 1, "rpc_cancelled": True, "process_group_reaped": True}


async def _wait_for_process_exit(pid: int) -> None:
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    raise RuntimeError("real cancellation probe left a child process running")


async def _run_controlled_subprocess(request, *, timeout_seconds: float) -> tuple[str, str]:
    """Run a real child process only through the active fake-broker scheduler."""

    _CANCELLATION_PID_PATH.unlink(missing_ok=True)
    command = [
        "/bin/sh",
        "-c",
        "sleep 60 & child=$!; "
        f"echo \"$$ $child\" > {_CANCELLATION_PID_PATH}; "
        "trap 'wait \"$child\"; exit 0' TERM; "
        "wait \"$child\"; echo synthetic",
    ]
    executor = CodexSubprocessExecutor(lambda _: command)
    return await executor.generate(request, timeout_seconds=timeout_seconds)


def _read_cancellation_pids(path: Path) -> tuple[int, int]:
    try:
        parent, child = path.read_text(encoding="utf-8").strip().split()
        return int(parent), int(child)
    except (OSError, ValueError) as error:
        raise RuntimeError("live cancellation probe did not record a process group") from error


async def _wait_for_cancellation_pids(path: Path) -> tuple[int, int]:
    for _ in range(100):
        if path.exists():
            try:
                return _read_cancellation_pids(path)
            except RuntimeError:
                pass
        await asyncio.sleep(0.05)
    raise RuntimeError("live cancellation probe did not record a process group")


def _request_for(*, operation: int, model: str, content: str = "synthetic request"):
    request = delivery_pb2.GenerateRequest(
        request_id=str(uuid.uuid4()),
        correlation_id="answer-delivery-compose",
        operation=operation,
        model_id=model,
        messages=[delivery_pb2.ChatMessage(role=delivery_pb2.USER, content=content)],
        output_contract=OPERATION_POLICIES[operation].output_contract,
    )
    if OPERATION_POLICIES[operation].evidence_required:
        request.evidence_snapshot.snapshot_sha256 = b"s" * 32
        request.evidence_snapshot.candidates.add(
            candidate_id="synthetic-candidate",
            book_id="synthetic-book",
            chunk_id="synthetic-chunk",
            source_sha256=b"h" * 32,
            scope_fingerprint="synthetic-scope",
            body_text_eligible=True,
            retrieval_provenance="compose-fixture",
            excerpt="Synthetic evidence.",
            source_revision="fixture-v1",
        )
    validate_generate_request(request)
    return request


def _metadata(token: str, release_sha: str):
    def values(request_id: str) -> tuple[tuple[str, str], ...]:
        return (
            ("authorization", f"Bearer {token}"),
            (_REQUEST_ID_HEADER, request_id),
            (_STACK_RELEASE_HEADER, release_sha),
        )

    return values


async def _expect_rpc_status(
    call, expected: grpc.StatusCode, *, error_code: int | None = None
) -> None:
    try:
        await call
    except grpc.aio.AioRpcError as error:
        if error.code() == expected:
            if error_code is not None and _error_code(error) != error_code:
                raise RuntimeError("broker returned an unexpected typed error detail") from error
            return
        raise RuntimeError(f"expected {expected.name}, got {error.code().name}") from error
    raise RuntimeError(f"expected {expected.name}, but the gRPC call succeeded")


def _error_code(error: grpc.aio.AioRpcError) -> int | None:
    """Read exactly the typed failure detail emitted by the active broker."""

    status = rpc_status.from_call(error)
    if status is None:
        return None
    for detail in status.details:
        parsed = delivery_pb2.ErrorDetail()
        if detail.Is(parsed.DESCRIPTOR):
            detail.Unpack(parsed)
            return parsed.code
    return None


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve-fake", "probe"))
    args = parser.parse_args(argv)
    if args.command == "serve-fake":
        asyncio.run(serve_fake())
        return 0
    print(json.dumps(asyncio.run(run_probes()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
