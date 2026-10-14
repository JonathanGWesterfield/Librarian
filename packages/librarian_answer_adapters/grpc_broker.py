"""Generated-stub gRPC adapters for the in-process answer runtime.

They are intentionally composition-root building blocks: M03 does not wire
them into chat or replace the legacy HTTP broker until every R2 caller can
switch atomically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import grpc
from grpc_status import rpc_status
from librarian_answer.models import (
    GenerationMessage,
    GenerationRequest,
    GenerationResult,
)
from librarian_answer.ports import RequestContext
from librarian_contracts.admission import OPERATION_POLICIES
from librarian_contracts.capabilities import (
    CapabilitiesContractMismatch,
    build_capabilities_request,
    required_operations_for_principal,
    validate_capabilities_response,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2_grpc as delivery_grpc,
)
from librarian_contracts.stack_contract import StackContract

_GRPC_MESSAGE_LIMIT_BYTES = 512 * 1024
_GRPC_MESSAGE_LIMIT_OPTIONS = (
    ("grpc.max_receive_message_length", _GRPC_MESSAGE_LIMIT_BYTES),
    ("grpc.max_send_message_length", _GRPC_MESSAGE_LIMIT_BYTES),
)
_REQUEST_ID_HEADER = "x-librarian-request-id"
_STACK_RELEASE_HEADER = "x-librarian-stack-release"
_ROLE_BY_NAME = {
    "system": delivery_pb2.SYSTEM,
    "user": delivery_pb2.USER,
    "assistant": delivery_pb2.ASSISTANT,
}


class GrpcBrokerClientError(RuntimeError):
    """A safe gRPC-broker failure with only typed public metadata."""

    def __init__(self, *, status: grpc.StatusCode, error_code: int | None) -> None:
        self.status = status
        self.error_code = error_code
        super().__init__(f"broker RPC failed with {status.name}")


@dataclass
class GeneratedGrpcBrokerClient:
    """One shared generated stub with an authenticated compatibility handshake."""

    channel: grpc.aio.Channel
    contract: StackContract
    principal: str
    bearer_token: str
    _stub: delivery_grpc.GenerationBrokerStub = field(init=False, repr=False)
    _ready: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.bearer_token:
            raise ValueError("gRPC broker clients require a bearer credential")
        self._stub = delivery_grpc.GenerationBrokerStub(self.channel)

    @classmethod
    def connect(
        cls,
        *,
        target: str,
        contract: StackContract,
        principal: str,
        bearer_token: str,
    ) -> GeneratedGrpcBrokerClient:
        """Create the process-shared aio channel used by one broker caller."""

        return cls(
            channel=grpc.aio.insecure_channel(
                target, options=_GRPC_MESSAGE_LIMIT_OPTIONS
            ),
            contract=contract,
            principal=principal,
            bearer_token=bearer_token,
        )

    async def ensure_ready(self, *, timeout: float | None = None) -> None:
        """Perform the release-bound, authenticated GetCapabilities handshake."""

        request = build_capabilities_request(self.contract)
        try:
            response = await self._stub.GetCapabilities(
                request,
                metadata=self._metadata(request_id="00000000-0000-4000-8000-000000000000"),
                timeout=timeout,
            )
        except grpc.RpcError as error:
            raise _client_error(error) from error
        try:
            validate_capabilities_response(
                response,
                contract=self.contract,
                required_operations=required_operations_for_principal(self.principal),
            )
        except CapabilitiesContractMismatch as error:
            raise GrpcBrokerClientError(
                status=grpc.StatusCode.FAILED_PRECONDITION,
                error_code=delivery_pb2.CONTRACT_MISMATCH,
            ) from error
        self._ready = True

    async def generate(
        self,
        request: delivery_pb2.GenerateRequest,
        *,
        timeout: float | None = None,
    ) -> delivery_pb2.GenerateResult:
        """Invoke the sole v1 execution RPC only after the handshake succeeds."""

        if not self._ready:
            raise GrpcBrokerClientError(
                status=grpc.StatusCode.FAILED_PRECONDITION,
                error_code=delivery_pb2.CONTRACT_MISMATCH,
            )
        try:
            return await self._stub.Generate(
                request,
                metadata=self._metadata(request_id=request.request_id),
                timeout=timeout,
            )
        except grpc.RpcError as error:
            raise _client_error(error) from error

    def _metadata(self, *, request_id: str) -> tuple[tuple[str, str], ...]:
        return (
            ("authorization", f"Bearer {self.bearer_token}"),
            (_REQUEST_ID_HEADER, request_id),
            (_STACK_RELEASE_HEADER, self.contract.stack_release_sha),
        )


@dataclass(frozen=True)
class GrpcRuntimeGenerationBroker:
    """Adapt one grounded synthesis, selection, or review operation to a port."""

    client: GeneratedGrpcBrokerClient
    operation: int
    output_contract: int
    model_id: str

    def __post_init__(self) -> None:
        policy = OPERATION_POLICIES.get(self.operation)
        if policy is None or policy.output_contract != self.output_contract:
            raise ValueError("operation and output contract are not a valid v1 pair")
        if self.operation not in {
            delivery_pb2.GROUNDED_SYNTHESIS,
            delivery_pb2.SEMANTIC_SOURCE_SELECTION,
            delivery_pb2.SUPPORT_REVIEW,
        }:
            raise ValueError("answer-runtime gRPC adapter only supports grounded operations")
        if not self.model_id:
            raise ValueError("answer-runtime gRPC adapter requires a model ID")

    async def generate(
        self, request: GenerationRequest, context: RequestContext
    ) -> GenerationResult:
        """Convert immutable runtime values to the generated v1 request type."""

        if context.is_cancelled():
            raise RuntimeError("answer request was cancelled before generation")
        result = await self.client.generate(
            _to_proto_request(
                request,
                operation=self.operation,
                output_contract=self.output_contract,
                model_id=self.model_id,
            ),
            timeout=context.remaining_seconds(),
        )
        if result.WhichOneof("outcome") == "invalid_structured_output":
            return GenerationResult(
                body="{}",
                provider="grpc",
                model=result.provider_model_id,
                repair_hint="invalid_structured_output",
                repairable=True,
            )
        if result.WhichOneof("outcome") != "success":
            raise RuntimeError("broker returned no generated result")
        return GenerationResult(
            body=result.success.content,
            provider="grpc",
            model=result.provider_model_id,
        )


def _to_proto_request(
    request: GenerationRequest,
    *,
    operation: int,
    output_contract: int,
    model_id: str,
) -> delivery_pb2.GenerateRequest:
    if not request.request_id:
        raise ValueError("runtime generation requests require an answer request ID")
    messages = [
        delivery_pb2.ChatMessage(
            role=_role(message),
            content=message.content,
        )
        for message in request.messages
    ]
    proto = delivery_pb2.GenerateRequest(
        request_id=request.request_id,
        correlation_id=request.request_id,
        operation=operation,
        model_id=model_id,
        messages=messages,
        output_contract=output_contract,
    )
    if request.evidence_snapshot:
        candidates = [
            delivery_pb2.EvidenceCandidate(
                candidate_id=item.candidate_id,
                book_id=item.book_id,
                chunk_id=item.chunk_id,
                source_sha256=bytes.fromhex(item.source_sha256),
                scope_fingerprint=_scope_fingerprint(item.effective_scope),
                body_text_eligible=item.body_text_eligible,
                retrieval_provenance=item.retrieval_provenance.get("backend", "runtime"),
                excerpt=item.excerpt,
                source_revision=item.source_revision,
            )
            for item in request.evidence_snapshot
        ]
        proto.evidence_snapshot.candidates.extend(candidates)
        proto.evidence_snapshot.snapshot_sha256 = _snapshot_digest(candidates)
    return proto


def _role(message: GenerationMessage) -> int:
    try:
        return _ROLE_BY_NAME[message.role]
    except KeyError as error:
        raise ValueError("runtime message role is not a v1 role") from error


def _snapshot_digest(candidates: list[delivery_pb2.EvidenceCandidate]) -> bytes:
    import hashlib

    return hashlib.sha256(
        b"".join(candidate.SerializeToString(deterministic=True) for candidate in candidates)
    ).digest()


def _scope_fingerprint(scope: object) -> str:
    items = getattr(scope, "items", None)
    if not callable(items):
        return "unscoped"
    rendered = "|".join(f"{key}={value}" for key, value in sorted(items()))
    return rendered or "unscoped"


def _client_error(error: grpc.RpcError) -> GrpcBrokerClientError:
    status = rpc_status.from_call(error)
    error_code: int | None = None
    if status is not None and len(status.details) == 1:
        detail = delivery_pb2.ErrorDetail()
        if status.details[0].Unpack(detail):
            error_code = detail.code
    return GrpcBrokerClientError(status=error.code(), error_code=error_code)
