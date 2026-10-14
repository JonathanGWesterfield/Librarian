"""Authenticated gRPC control-plane foundation for the Codex broker.

This module intentionally coexists with the R0 HTTP application while M03 is
being built.  It exposes only Health and GetCapabilities here; provider
execution is added behind the same service in the next slice.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_status import rpc_status
from librarian_contracts.admission import (
    OPERATION_POLICIES,
    ContractViolation,
    GeneratedResultViolation,
    build_failure_status,
    is_operation_allowed,
    validate_generate_request,
    validate_generate_result,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2_grpc as delivery_grpc,
)
from librarian_contracts.stack_contract import StackContract

from librarian_broker.execution import (
    BrokerAdmissionFull,
    BrokerDeadlineExceeded,
    BrokerExecutionFailed,
    BrokerScheduler,
)

_AUTHORIZATION_HEADER = "authorization"
_REQUEST_ID_HEADER = "x-librarian-request-id"
_STACK_RELEASE_HEADER = "x-librarian-stack-release"
_REQUEST_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)
_HEALTH_PRINCIPAL = "compose-health"


@dataclass(frozen=True)
class BrokerCredentials:
    """Bearer credentials keyed by their server-derived service principal."""

    tokens_by_principal: Mapping[str, str]

    def authenticate(self, metadata: Mapping[str, tuple[str, ...]]) -> str | None:
        """Return the principal for one exact bearer credential, if any."""

        values = metadata.get(_AUTHORIZATION_HEADER, ())
        if len(values) != 1:
            return None
        scheme, separator, token = values[0].partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or not token:
            return None
        for principal, expected_token in self.tokens_by_principal.items():
            if expected_token and hmac.compare_digest(token, expected_token):
                return principal
        return None


class GenerationBrokerService(delivery_grpc.GenerationBrokerServicer):
    """v1 authenticated compatibility endpoint backed by an immutable manifest."""

    def __init__(
        self,
        *,
        contract: StackContract,
        credentials: BrokerCredentials,
        scheduler: BrokerScheduler | None = None,
    ) -> None:
        self._contract = contract
        self._credentials = credentials
        self._scheduler = scheduler

    async def GetCapabilities(
        self,
        request: delivery_pb2.CapabilitiesRequest,
        context: grpc.aio.ServicerContext,
    ) -> delivery_pb2.Capabilities:
        """Authenticate and prove stack compatibility before any execution RPC."""

        metadata = _metadata(context)
        request_id = _request_id(metadata)
        principal = self._credentials.authenticate(metadata)
        if principal is None:
            await _abort(
                context,
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
                request_id,
            )
        if not _has_exact_value(metadata, _STACK_RELEASE_HEADER, request.stack_release_sha):
            await _abort(
                context,
                grpc.StatusCode.FAILED_PRECONDITION,
                delivery_pb2.CONTRACT_MISMATCH,
                request_id,
            )
        if not _is_compatible_request(request, self._contract):
            await _abort(
                context,
                grpc.StatusCode.FAILED_PRECONDITION,
                delivery_pb2.CONTRACT_MISMATCH,
                request_id,
            )
        return delivery_pb2.Capabilities(
            contract_major=self._contract.contract_major,
            min_contract_minor=self._contract.contract_minor,
            max_contract_minor=self._contract.contract_minor,
            descriptor_sha256=bytes.fromhex(self._contract.descriptor_sha256),
            stack_release_sha=self._contract.stack_release_sha,
            operations=sorted(OPERATION_POLICIES),
        )

    async def Generate(
        self,
        request: delivery_pb2.GenerateRequest,
        context: grpc.aio.ServicerContext,
    ) -> delivery_pb2.GenerateResult:
        """Validate, authorize, and schedule exactly one provider execution."""

        metadata = _metadata(context)
        request_id = (
            request.request_id if _REQUEST_ID_PATTERN.fullmatch(request.request_id) else ""
        )
        principal = self._credentials.authenticate(metadata)
        if principal is None:
            await _abort(
                context,
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
                request_id,
            )
        if not _has_exact_value(
            metadata, _STACK_RELEASE_HEADER, self._contract.stack_release_sha
        ):
            await _abort(
                context,
                grpc.StatusCode.FAILED_PRECONDITION,
                delivery_pb2.CONTRACT_MISMATCH,
                request_id,
            )
        try:
            validate_generate_request(request)
        except ContractViolation as error:
            await _abort(
                context,
                error.grpc_status,
                error.error_code,
                error.request_id,
            )
        if not is_operation_allowed(principal=principal, operation=request.operation):
            await _abort(
                context,
                grpc.StatusCode.PERMISSION_DENIED,
                delivery_pb2.OPERATION_DENIED,
                request_id,
            )
        if self._scheduler is None:
            await _abort(
                context,
                grpc.StatusCode.FAILED_PRECONDITION,
                delivery_pb2.BROKER_NOT_READY,
                request_id,
            )
        try:
            execution = await self._scheduler.execute(
                request, deadline_seconds=context.time_remaining()
            )
        except BrokerAdmissionFull:
            await _abort(
                context,
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                delivery_pb2.ADMISSION_FULL,
                request_id,
            )
        except BrokerDeadlineExceeded:
            await _abort(
                context,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                delivery_pb2.EXECUTION_TIMEOUT,
                request_id,
            )
        except BrokerExecutionFailed:
            await _abort(
                context,
                grpc.StatusCode.INTERNAL,
                delivery_pb2.EXECUTION_FAILED,
                request_id,
            )

        result = delivery_pb2.GenerateResult(
            request_id=request.request_id,
            provider_model_id=execution.provider_model_id,
            queue_wait_ms=execution.queue_wait_ms,
            execution_ms=execution.execution_ms,
            success=delivery_pb2.GenerationSuccess(content=execution.content),
        )
        try:
            validate_generate_result(result)
        except GeneratedResultViolation as error:
            result.ClearField("success")
            result.invalid_structured_output.violation = error.output_violation
        return result


class AuthenticatedHealthService(health_pb2_grpc.HealthServicer):
    """Expose standard gRPC Health only to the dedicated health identity."""

    def __init__(self, credentials: BrokerCredentials, *, serving: bool = True) -> None:
        self._credentials = credentials
        self._serving = serving

    async def Check(
        self,
        request: health_pb2.HealthCheckRequest,
        context: grpc.aio.ServicerContext,
    ) -> health_pb2.HealthCheckResponse:
        metadata = _metadata(context)
        request_id = _request_id(metadata)
        if self._credentials.authenticate(metadata) != _HEALTH_PRINCIPAL:
            await _abort(
                context,
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
                request_id,
            )
        status = (
            health_pb2.HealthCheckResponse.SERVING
            if self._serving
            else health_pb2.HealthCheckResponse.NOT_SERVING
        )
        return health_pb2.HealthCheckResponse(status=status)


def add_services_to_server(
    server: grpc.aio.Server,
    *,
    contract: StackContract,
    credentials: BrokerCredentials,
    scheduler: BrokerScheduler | None = None,
    serving: bool = True,
) -> None:
    """Register the authenticated v1 and standard Health services on one server."""

    delivery_grpc.add_GenerationBrokerServicer_to_server(
        GenerationBrokerService(
            contract=contract,
            credentials=credentials,
            scheduler=scheduler,
        ),
        server,
    )
    health_pb2_grpc.add_HealthServicer_to_server(
        AuthenticatedHealthService(credentials, serving=serving), server
    )


def _metadata(context: grpc.aio.ServicerContext) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for key, value in context.invocation_metadata():
        values.setdefault(key.casefold(), []).append(value)
    return {key: tuple(value) for key, value in values.items()}


def _request_id(metadata: Mapping[str, tuple[str, ...]]) -> str:
    values = metadata.get(_REQUEST_ID_HEADER, ())
    if len(values) != 1 or not _REQUEST_ID_PATTERN.fullmatch(values[0]):
        return ""
    return values[0]


def _has_exact_value(
    metadata: Mapping[str, tuple[str, ...]], key: str, expected: str
) -> bool:
    return metadata.get(key, ()) == (expected,)


def _is_compatible_request(
    request: delivery_pb2.CapabilitiesRequest, contract: StackContract
) -> bool:
    return (
        request.contract_major == contract.contract_major
        and request.contract_minor == contract.contract_minor
        and request.descriptor_sha256 == bytes.fromhex(contract.descriptor_sha256)
        and request.stack_release_sha == contract.stack_release_sha
    )


async def _abort(
    context: grpc.aio.ServicerContext,
    status_code: grpc.StatusCode,
    error_code: int,
    request_id: str,
) -> None:
    status = build_failure_status(
        grpc_status=status_code,
        error_code=error_code,
        request_id=request_id,
    )
    await context.abort_with_status(rpc_status.to_status(status))
