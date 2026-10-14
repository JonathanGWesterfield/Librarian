"""Authenticated gRPC control-plane foundation for the Codex broker.

This module intentionally coexists with the R0 HTTP application while M03 is
being built. Its generated-stub service exposes Health, GetCapabilities, and
the bounded unary Generate path without changing existing HTTP callers.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

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
_MAX_GRPC_MESSAGE_BYTES = 512 * 1024
_GRPC_MESSAGE_LIMIT_OPTIONS = (
    ("grpc.max_receive_message_length", _MAX_GRPC_MESSAGE_BYTES),
    ("grpc.max_send_message_length", _MAX_GRPC_MESSAGE_BYTES),
)
_CAPABILITIES_METHOD = "/librarian.answer.v1.GenerationBroker/GetCapabilities"
_GENERATE_METHOD = "/librarian.answer.v1.GenerationBroker/Generate"
_HEALTH_METHOD = "/grpc.health.v1.Health/Check"
_APPLICATION_METHODS = frozenset(
    {_CAPABILITIES_METHOD, _GENERATE_METHOD, _HEALTH_METHOD}
)
_RELEASE_BOUND_METHODS = frozenset({_CAPABILITIES_METHOD, _GENERATE_METHOD})
_APPLICATION_METADATA_KEYS = frozenset(
    {_AUTHORIZATION_HEADER, _REQUEST_ID_HEADER, _STACK_RELEASE_HEADER}
)
_STANDARD_METADATA_KEYS = frozenset(
    {
        "content-type",
        "grpc-accept-encoding",
        "grpc-encoding",
        "grpc-message",
        "grpc-previous-rpc-attempts",
        "grpc-retry-pushback-ms",
        "grpc-status",
        "grpc-status-details-bin",
        "grpc-tags-bin",
        "grpc-timeout",
        "te",
        "user-agent",
    }
)


@dataclass(frozen=True)
class _CallIdentity:
    """Authenticated metadata preserved from the transport admission gate."""

    principal: str
    metadata: Mapping[str, tuple[str, ...]]
    request_id: str


_CALL_IDENTITY: ContextVar[_CallIdentity | None] = ContextVar(
    "librarian_broker_call_identity", default=None
)


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


class BrokerMetadataAdmissionInterceptor(grpc.aio.ServerInterceptor):
    """Reject invalid broker metadata before protobuf deserialization."""

    def __init__(self, credentials: BrokerCredentials) -> None:
        self._credentials = credentials

    async def intercept_service(
        self,
        continuation: Any,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        method = handler_call_details.method
        if method not in _APPLICATION_METHODS:
            return await continuation(handler_call_details)

        metadata = _metadata_values(handler_call_details.invocation_metadata or ())
        identity, error = _admit_metadata(
            method=method, metadata=metadata, credentials=self._credentials
        )
        if error is not None:
            return _rejection_handler(*error)

        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler

        async def invoke(request: object, context: grpc.aio.ServicerContext) -> object:
            token = _CALL_IDENTITY.set(identity)
            try:
                return await handler.unary_unary(request, context)
            finally:
                _CALL_IDENTITY.reset(token)

        return grpc.unary_unary_rpc_method_handler(
            invoke,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


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

        identity = _CALL_IDENTITY.get()
        if identity is None:
            await _abort(
                context,
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
                "",
            )
        metadata = identity.metadata
        request_id = identity.request_id
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

        identity = _CALL_IDENTITY.get()
        if identity is None:
            await _abort(
                context,
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
                "",
            )
        metadata = identity.metadata
        request_id = identity.request_id
        if request.request_id != request_id:
            await _abort(
                context,
                grpc.StatusCode.INVALID_ARGUMENT,
                delivery_pb2.REQUEST_LIMIT_EXCEEDED,
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
        if request.operation in OPERATION_POLICIES and not is_operation_allowed(
            principal=identity.principal, operation=request.operation
        ):
            await _abort(
                context,
                grpc.StatusCode.PERMISSION_DENIED,
                delivery_pb2.OPERATION_DENIED,
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
        identity = _CALL_IDENTITY.get()
        if identity is None or identity.principal != _HEALTH_PRINCIPAL:
            await _abort(
                context,
                grpc.StatusCode.UNAUTHENTICATED,
                delivery_pb2.CALLER_DENIED,
                identity.request_id if identity is not None else "",
            )
        status = (
            health_pb2.HealthCheckResponse.SERVING
            if self._serving
            else health_pb2.HealthCheckResponse.NOT_SERVING
        )
        return health_pb2.HealthCheckResponse(status=status)


def create_broker_server(
    *,
    contract: StackContract,
    credentials: BrokerCredentials,
    scheduler: BrokerScheduler | None = None,
    serving: bool = True,
) -> grpc.aio.Server:
    """Create the sole bounded, authenticated v1 broker transport."""

    server = grpc.aio.server(
        interceptors=(BrokerMetadataAdmissionInterceptor(credentials),),
        options=_GRPC_MESSAGE_LIMIT_OPTIONS,
    )

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
    return server


def _metadata_values(
    invocation_metadata: tuple[tuple[str, str | bytes], ...],
) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for key, value in invocation_metadata:
        if isinstance(value, str):
            values.setdefault(key.casefold(), []).append(value)
        else:
            values.setdefault(key.casefold(), []).append("")
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


def _admit_metadata(
    *,
    method: str,
    metadata: Mapping[str, tuple[str, ...]],
    credentials: BrokerCredentials,
) -> tuple[_CallIdentity | None, tuple[grpc.StatusCode, int, str] | None]:
    """Authenticate and bound app metadata before protobuf request parsing."""

    request_id = _request_id(metadata)
    principal = credentials.authenticate(metadata)
    if principal is None:
        return None, (grpc.StatusCode.UNAUTHENTICATED, delivery_pb2.CALLER_DENIED, request_id)
    if any(
        key not in _APPLICATION_METADATA_KEYS and key not in _STANDARD_METADATA_KEYS
        for key in metadata
    ):
        return None, (
            grpc.StatusCode.INVALID_ARGUMENT,
            delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            request_id,
        )
    if method in _RELEASE_BOUND_METHODS and (
        not request_id
        or not _has_single_value(metadata, _STACK_RELEASE_HEADER)
    ):
        return None, (
            grpc.StatusCode.INVALID_ARGUMENT,
            delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            request_id,
        )
    return _CallIdentity(principal, metadata, request_id), None


def _has_single_value(metadata: Mapping[str, tuple[str, ...]], key: str) -> bool:
    return len(metadata.get(key, ())) == 1 and bool(metadata[key][0])


def _rejection_handler(
    status_code: grpc.StatusCode,
    error_code: int,
    request_id: str,
) -> grpc.RpcMethodHandler:
    """Create a no-deserialization unary rejection with a typed status detail."""

    async def reject(_: bytes, context: grpc.aio.ServicerContext) -> None:
        await _abort(context, status_code, error_code, request_id)

    return grpc.unary_unary_rpc_method_handler(reject, request_deserializer=lambda _: None)


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
