"""v1 broker admission rules and standardized non-OK failure details.

This module is transport-neutral so the future gRPC service can apply the same
rules before queue admission and use the same `google.rpc.Status` trailer for
every rejected request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import grpc
from google.protobuf import any_pb2
from google.rpc import status_pb2

from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)

KIB = 1024
MAX_MESSAGES = 128
MAX_MESSAGE_UTF8_BYTES = 32 * KIB
MAX_TOTAL_MESSAGE_UTF8_BYTES = 192 * KIB
MAX_EVIDENCE_CANDIDATES = 32
MAX_EXCERPT_UTF8_BYTES = 8 * KIB
MAX_SNAPSHOT_SERIALIZED_BYTES = 256 * KIB
MAX_REQUEST_SERIALIZED_BYTES = 512 * KIB
MAX_RESULT_SERIALIZED_BYTES = 128 * KIB
MAX_GENERATED_CONTENT_UTF8_BYTES = 96 * KIB
_MAX_CORRELATION_ID_LENGTH = 128
_MAX_MODEL_ID_UTF8_BYTES = 256
_MAX_SOURCE_REVISION_LENGTH = 128
_CANONICAL_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)


@dataclass(frozen=True)
class OperationPolicy:
    """The one allowed output contract and evidence rule for an operation."""

    output_contract: int
    evidence_required: bool
    permitted_principals: frozenset[str]


@dataclass(frozen=True)
class FailurePolicy:
    """A bounded public detail for one permitted gRPC status/code pair."""

    safe_message: str
    retryable: bool


OPERATION_POLICIES = {
    delivery_pb2.GROUNDED_SYNTHESIS: OperationPolicy(
        output_contract=delivery_pb2.GROUNDED_ANSWER_JSON_V1,
        evidence_required=True,
        permitted_principals=frozenset({"api", "answer-runtime"}),
    ),
    delivery_pb2.SEMANTIC_SOURCE_SELECTION: OperationPolicy(
        output_contract=delivery_pb2.SOURCE_SELECTION_JSON_V1,
        evidence_required=True,
        permitted_principals=frozenset({"api", "answer-runtime"}),
    ),
    delivery_pb2.SUPPORT_REVIEW: OperationPolicy(
        output_contract=delivery_pb2.SUPPORT_REVIEW_JSON_V1,
        evidence_required=True,
        permitted_principals=frozenset({"api", "answer-runtime"}),
    ),
    delivery_pb2.EVALUATOR_JUDGEMENT: OperationPolicy(
        output_contract=delivery_pb2.EVALUATOR_VERDICT_JSON_V1,
        evidence_required=False,
        permitted_principals=frozenset({"evaluator"}),
    ),
    delivery_pb2.CHAPTER_SUMMARIZATION: OperationPolicy(
        output_contract=delivery_pb2.PLAIN_TEXT_V1,
        evidence_required=False,
        permitted_principals=frozenset({"api", "summary-worker"}),
    ),
    delivery_pb2.BOOK_SUMMARIZATION: OperationPolicy(
        output_contract=delivery_pb2.PLAIN_TEXT_V1,
        evidence_required=False,
        permitted_principals=frozenset({"api", "summary-worker"}),
    ),
    delivery_pb2.TAG_GENERATION: OperationPolicy(
        output_contract=delivery_pb2.TAGS_JSON_V1,
        evidence_required=False,
        permitted_principals=frozenset({"metadata-worker"}),
    ),
    delivery_pb2.GENRE_GENERATION: OperationPolicy(
        output_contract=delivery_pb2.GENRES_JSON_V1,
        evidence_required=False,
        permitted_principals=frozenset({"api", "metadata-worker"}),
    ),
    delivery_pb2.RECOMMENDATION_SYNTHESIS: OperationPolicy(
        output_contract=delivery_pb2.PLAIN_TEXT_V1,
        evidence_required=False,
        permitted_principals=frozenset({"api"}),
    ),
}
_OUTPUT_CONTRACTS = frozenset(policy.output_contract for policy in OPERATION_POLICIES.values())
_MESSAGE_ROLES = frozenset(
    {
        delivery_pb2.SYSTEM,
        delivery_pb2.USER,
        delivery_pb2.ASSISTANT,
    }
)
FAILURE_POLICIES = {
    (grpc.StatusCode.UNAUTHENTICATED, delivery_pb2.CALLER_DENIED): FailurePolicy(
        safe_message="The caller is not authorized to use the generation broker.",
        retryable=False,
    ),
    (grpc.StatusCode.PERMISSION_DENIED, delivery_pb2.CALLER_DENIED): FailurePolicy(
        safe_message="The caller is not authorized to use the generation broker.",
        retryable=False,
    ),
    (grpc.StatusCode.PERMISSION_DENIED, delivery_pb2.OPERATION_DENIED): FailurePolicy(
        safe_message="The caller is not authorized for this generation operation.",
        retryable=False,
    ),
    (grpc.StatusCode.INVALID_ARGUMENT, delivery_pb2.REQUEST_LIMIT_EXCEEDED): FailurePolicy(
        safe_message="The request does not satisfy the v1 broker contract.",
        retryable=False,
    ),
    (grpc.StatusCode.INVALID_ARGUMENT, delivery_pb2.UNKNOWN_ENUM): FailurePolicy(
        safe_message="The request contains an unsupported v1 enum value.",
        retryable=False,
    ),
    (grpc.StatusCode.FAILED_PRECONDITION, delivery_pb2.CONTRACT_MISMATCH): FailurePolicy(
        safe_message="The caller and broker contracts are incompatible.",
        retryable=False,
    ),
    (grpc.StatusCode.FAILED_PRECONDITION, delivery_pb2.BROKER_NOT_READY): FailurePolicy(
        safe_message="The generation broker is not ready.",
        retryable=False,
    ),
    (grpc.StatusCode.RESOURCE_EXHAUSTED, delivery_pb2.ADMISSION_FULL): FailurePolicy(
        safe_message="The generation broker is at capacity.",
        retryable=True,
    ),
    (grpc.StatusCode.DEADLINE_EXCEEDED, delivery_pb2.EXECUTION_TIMEOUT): FailurePolicy(
        safe_message="The generation request did not finish before its deadline.",
        retryable=False,
    ),
    (grpc.StatusCode.CANCELLED, delivery_pb2.EXECUTION_TIMEOUT): FailurePolicy(
        safe_message="The generation request was cancelled.",
        retryable=False,
    ),
    (grpc.StatusCode.UNAVAILABLE, delivery_pb2.BROKER_NOT_READY): FailurePolicy(
        safe_message="The generation broker is temporarily unavailable.",
        retryable=True,
    ),
    (grpc.StatusCode.INTERNAL, delivery_pb2.EXECUTION_FAILED): FailurePolicy(
        safe_message="The generation broker could not complete the request.",
        retryable=False,
    ),
}


class ContractViolation(ValueError):
    """A pre-admission contract violation that cannot reach a provider process."""

    def __init__(self, *, error_code: int, request_id: str) -> None:
        self.grpc_status = grpc.StatusCode.INVALID_ARGUMENT
        self.error_code = error_code
        self.request_id = _safe_request_id(request_id)
        super().__init__(_failure_policy(self.grpc_status, error_code).safe_message)

    def as_rpc_status(self) -> status_pb2.Status:
        """Encode the one mandated `ErrorDetail` for gRPC trailing metadata."""

        return build_failure_status(
            grpc_status=self.grpc_status,
            error_code=self.error_code,
            request_id=self.request_id,
        )


class GeneratedResultViolation(ValueError):
    """A broker result that must become an OK invalid-structured-output result."""

    def __init__(self, output_violation: int) -> None:
        self.output_violation = output_violation
        super().__init__("The generated result violates the v1 output contract.")


def validate_generate_request(request: delivery_pb2.GenerateRequest) -> None:
    """Reject a malformed v1 request before broker queue admission."""

    request_id = request.request_id
    if request.ByteSize() > MAX_REQUEST_SERIALIZED_BYTES:
        _reject_limit(request_id)
    if not _is_canonical_uuid(request_id):
        _reject_limit(request_id)
    if not _is_ascii_with_length(request.correlation_id, _MAX_CORRELATION_ID_LENGTH):
        _reject_limit(request_id)
    if not _has_utf8_length(request.model_id, _MAX_MODEL_ID_UTF8_BYTES):
        _reject_limit(request_id)

    policy = OPERATION_POLICIES.get(request.operation)
    if policy is None:
        _reject_unknown_enum(request_id)
    if request.output_contract not in _OUTPUT_CONTRACTS:
        _reject_unknown_enum(request_id)
    if request.output_contract != policy.output_contract:
        _reject_limit(request_id)

    _validate_messages(request, request_id)
    _validate_evidence(request, policy, request_id)


def is_operation_allowed(*, principal: str, operation: int) -> bool:
    """Return whether a credential-derived principal may invoke an operation."""

    policy = OPERATION_POLICIES.get(operation)
    return policy is not None and principal in policy.permitted_principals


def validate_generate_result(result: delivery_pb2.GenerateResult) -> None:
    """Validate an outbound result before it crosses the 128 KiB gRPC boundary."""

    if result.ByteSize() > MAX_RESULT_SERIALIZED_BYTES:
        _reject_generated_result(delivery_pb2.TOO_LARGE)

    outcome = result.WhichOneof("outcome")
    if outcome is None:
        _reject_generated_result(delivery_pb2.MALFORMED)
    if outcome == "success":
        if len(result.success.content.encode("utf-8")) > MAX_GENERATED_CONTENT_UTF8_BYTES:
            _reject_generated_result(delivery_pb2.TOO_LARGE)
        return
    if outcome == "invalid_structured_output":
        if result.invalid_structured_output.violation not in {
            delivery_pb2.MALFORMED,
            delivery_pb2.TOO_LARGE,
        }:
            _reject_generated_result(delivery_pb2.MALFORMED)
        return
    _reject_generated_result(delivery_pb2.MALFORMED)


def build_failure_status(
    *,
    grpc_status: grpc.StatusCode,
    error_code: int,
    request_id: str,
) -> status_pb2.Status:
    """Build a standard status containing exactly one bounded `ErrorDetail`."""

    policy = _failure_policy(grpc_status, error_code)
    detail = delivery_pb2.ErrorDetail(
        code=error_code,
        retryable=policy.retryable,
        retry_after_ms=0,
        safe_message=policy.safe_message,
        request_id=_safe_request_id(request_id),
    )
    packed_detail = any_pb2.Any()
    packed_detail.Pack(detail)
    return status_pb2.Status(
        code=grpc_status.value[0],
        message=policy.safe_message,
        details=[packed_detail],
    )


def _validate_messages(
    request: delivery_pb2.GenerateRequest,
    request_id: str,
) -> None:
    if len(request.messages) > MAX_MESSAGES:
        _reject_limit(request_id)

    total_bytes = 0
    for message in request.messages:
        if message.role not in _MESSAGE_ROLES:
            _reject_unknown_enum(request_id)
        content_bytes = len(message.content.encode("utf-8"))
        if content_bytes > MAX_MESSAGE_UTF8_BYTES:
            _reject_limit(request_id)
        total_bytes += content_bytes
        if total_bytes > MAX_TOTAL_MESSAGE_UTF8_BYTES:
            _reject_limit(request_id)


def _validate_evidence(
    request: delivery_pb2.GenerateRequest,
    policy: OperationPolicy,
    request_id: str,
) -> None:
    has_snapshot = request.HasField("evidence_snapshot")
    if policy.evidence_required:
        if not has_snapshot or not request.evidence_snapshot.candidates:
            _reject_limit(request_id)
    elif has_snapshot:
        _reject_limit(request_id)
    else:
        return

    snapshot = request.evidence_snapshot
    if len(snapshot.candidates) > MAX_EVIDENCE_CANDIDATES:
        _reject_limit(request_id)
    if len(snapshot.snapshot_sha256) != 32:
        _reject_limit(request_id)
    if snapshot.ByteSize() > MAX_SNAPSHOT_SERIALIZED_BYTES:
        _reject_limit(request_id)

    for candidate in snapshot.candidates:
        if not candidate.body_text_eligible:
            _reject_limit(request_id)
        if not all(
            (
                candidate.candidate_id,
                candidate.book_id,
                candidate.chunk_id,
                candidate.scope_fingerprint,
                candidate.retrieval_provenance,
            )
        ):
            _reject_limit(request_id)
        if len(candidate.source_sha256) != 32:
            _reject_limit(request_id)
        if not _is_ascii_with_length(
            candidate.source_revision, _MAX_SOURCE_REVISION_LENGTH
        ):
            _reject_limit(request_id)
        if len(candidate.excerpt.encode("utf-8")) > MAX_EXCERPT_UTF8_BYTES:
            _reject_limit(request_id)


def _failure_policy(
    grpc_status: grpc.StatusCode,
    error_code: int,
) -> FailurePolicy:
    policy = FAILURE_POLICIES.get((grpc_status, error_code))
    if policy is None:
        raise ValueError(
            f"{grpc_status.name} is not permitted with ErrorDetail code {error_code}"
        )
    return policy


def _is_canonical_uuid(value: str) -> bool:
    return bool(_CANONICAL_UUID.fullmatch(value))


def _safe_request_id(value: str) -> str:
    return value if _is_canonical_uuid(value) else ""


def _is_ascii_with_length(value: str, maximum_length: int) -> bool:
    return 1 <= len(value) <= maximum_length and value.isascii()


def _has_utf8_length(value: str, maximum_bytes: int) -> bool:
    return 1 <= len(value.encode("utf-8")) <= maximum_bytes


def _reject_limit(request_id: str) -> None:
    raise ContractViolation(
        error_code=delivery_pb2.REQUEST_LIMIT_EXCEEDED,
        request_id=request_id,
    )


def _reject_unknown_enum(request_id: str) -> None:
    raise ContractViolation(
        error_code=delivery_pb2.UNKNOWN_ENUM,
        request_id=request_id,
    )


def _reject_generated_result(output_violation: int) -> None:
    raise GeneratedResultViolation(output_violation)
