"""Tests for executable pre-admission v1 broker contract rules."""

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

import grpc
from google.rpc import status_pb2

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.admission import (
    FAILURE_POLICIES,
    MAX_EVIDENCE_CANDIDATES,
    MAX_EXCERPT_UTF8_BYTES,
    MAX_GENERATED_CONTENT_UTF8_BYTES,
    MAX_MESSAGE_UTF8_BYTES,
    MAX_MESSAGES,
    MAX_REQUEST_SERIALIZED_BYTES,
    MAX_RESULT_SERIALIZED_BYTES,
    MAX_SNAPSHOT_SERIALIZED_BYTES,
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


class AdmissionPolicyTests(unittest.TestCase):
    """Keep documented v1 admission and failure rules executable before M03."""

    def test_every_operation_accepts_its_one_contract_and_evidence_rule(self) -> None:
        for operation, policy in OPERATION_POLICIES.items():
            with self.subTest(operation=operation):
                request = _request_for(operation, policy.output_contract)
                if policy.evidence_required:
                    _add_evidence(request)

                validate_generate_request(request)

    def test_mismatch_missing_evidence_and_forbidden_evidence_are_rejected(self) -> None:
        required_operation = delivery_pb2.GROUNDED_SYNTHESIS
        required_policy = OPERATION_POLICIES[required_operation]
        missing_evidence = _request_for(required_operation, required_policy.output_contract)
        mismatched_output = _request_for(required_operation, delivery_pb2.PLAIN_TEXT_V1)
        _add_evidence(mismatched_output)
        forbidden_evidence = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            delivery_pb2.PLAIN_TEXT_V1,
        )
        _add_evidence(forbidden_evidence)

        for request in (missing_evidence, mismatched_output, forbidden_evidence):
            self._assert_rejection(request, delivery_pb2.REQUEST_LIMIT_EXCEEDED)

    def test_unknown_or_unspecified_enums_are_rejected_as_unknown_enum(self) -> None:
        unknown_operation = _request_for(99, delivery_pb2.PLAIN_TEXT_V1)
        unknown_output = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            99,
        )
        unspecified_role = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            delivery_pb2.PLAIN_TEXT_V1,
        )
        unspecified_role.messages[0].role = delivery_pb2.MESSAGE_ROLE_UNSPECIFIED

        for request in (unknown_operation, unknown_output, unspecified_role):
            self._assert_rejection(request, delivery_pb2.UNKNOWN_ENUM)

    def test_request_message_and_evidence_size_limits_are_enforced(self) -> None:
        too_many_messages = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            delivery_pb2.PLAIN_TEXT_V1,
        )
        too_many_messages.messages.extend(
            deepcopy(too_many_messages.messages[0]) for _ in range(MAX_MESSAGES)
        )

        oversized_message = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            delivery_pb2.PLAIN_TEXT_V1,
        )
        oversized_message.messages[0].content = "x" * (MAX_MESSAGE_UTF8_BYTES + 1)

        oversized_total_messages = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            delivery_pb2.PLAIN_TEXT_V1,
        )
        oversized_total_messages.messages[0].content = "x" * MAX_MESSAGE_UTF8_BYTES
        oversized_total_messages.messages.extend(
            deepcopy(oversized_total_messages.messages[0]) for _ in range(6)
        )

        too_many_candidates = _request_for(
            delivery_pb2.GROUNDED_SYNTHESIS,
            delivery_pb2.GROUNDED_ANSWER_JSON_V1,
        )
        for _ in range(MAX_EVIDENCE_CANDIDATES + 1):
            _add_evidence(too_many_candidates)

        oversized_excerpt = _request_for(
            delivery_pb2.GROUNDED_SYNTHESIS,
            delivery_pb2.GROUNDED_ANSWER_JSON_V1,
        )
        _add_evidence(oversized_excerpt, excerpt="x" * (MAX_EXCERPT_UTF8_BYTES + 1))

        oversized_snapshot = _request_for(
            delivery_pb2.GROUNDED_SYNTHESIS,
            delivery_pb2.GROUNDED_ANSWER_JSON_V1,
        )
        for _ in range(MAX_EVIDENCE_CANDIDATES):
            _add_evidence(oversized_snapshot, excerpt="x" * MAX_EXCERPT_UTF8_BYTES)
        self.assertGreater(
            oversized_snapshot.evidence_snapshot.ByteSize(), MAX_SNAPSHOT_SERIALIZED_BYTES
        )

        oversized_request = _request_for(
            delivery_pb2.CHAPTER_SUMMARIZATION,
            delivery_pb2.PLAIN_TEXT_V1,
        )
        oversized_request.model_id = "x" * MAX_REQUEST_SERIALIZED_BYTES

        for request in (
            too_many_messages,
            oversized_message,
            oversized_total_messages,
            too_many_candidates,
            oversized_excerpt,
            oversized_snapshot,
            oversized_request,
        ):
            self._assert_rejection(request, delivery_pb2.REQUEST_LIMIT_EXCEEDED)

    def test_required_identity_hash_and_string_fields_are_enforced(self) -> None:
        valid = _request_for(
            delivery_pb2.GROUNDED_SYNTHESIS,
            delivery_pb2.GROUNDED_ANSWER_JSON_V1,
        )
        _add_evidence(valid)

        invalid_requests = []
        for mutation in (
            lambda request: setattr(request, "request_id", "not-a-uuid"),
            lambda request: setattr(request, "correlation_id", "é"),
            lambda request: setattr(request, "correlation_id", "x" * 129),
            lambda request: setattr(request, "model_id", ""),
            lambda request: setattr(request, "model_id", "x" * 257),
            lambda request: setattr(request.evidence_snapshot, "snapshot_sha256", b"x" * 31),
            lambda request: setattr(
                request.evidence_snapshot.candidates[0], "source_sha256", b"x" * 31
            ),
            lambda request: setattr(
                request.evidence_snapshot.candidates[0], "source_revision", "é"
            ),
            lambda request: setattr(
                request.evidence_snapshot.candidates[0], "candidate_id", ""
            ),
            lambda request: setattr(
                request.evidence_snapshot.candidates[0], "body_text_eligible", False
            ),
        ):
            request = deepcopy(valid)
            mutation(request)
            invalid_requests.append(request)

        for request in invalid_requests:
            self._assert_rejection(request, delivery_pb2.REQUEST_LIMIT_EXCEEDED)

    def test_authorization_matrix_is_allow_listed(self) -> None:
        expected = {
            delivery_pb2.GROUNDED_SYNTHESIS: {"api", "answer-runtime"},
            delivery_pb2.SEMANTIC_SOURCE_SELECTION: {"api", "answer-runtime"},
            delivery_pb2.SUPPORT_REVIEW: {"api", "answer-runtime"},
            delivery_pb2.EVALUATOR_JUDGEMENT: {"evaluator"},
            delivery_pb2.CHAPTER_SUMMARIZATION: {"api", "summary-worker"},
            delivery_pb2.BOOK_SUMMARIZATION: {"api", "summary-worker"},
            delivery_pb2.TAG_GENERATION: {"metadata-worker"},
            delivery_pb2.GENRE_GENERATION: {"api", "metadata-worker"},
            delivery_pb2.RECOMMENDATION_SYNTHESIS: {"api"},
        }

        for operation, principals in expected.items():
            for principal in (
                "api",
                "answer-runtime",
                "summary-worker",
                "metadata-worker",
                "evaluator",
            ):
                with self.subTest(operation=operation, principal=principal):
                    self.assertEqual(
                        is_operation_allowed(principal=principal, operation=operation),
                        principal in principals,
                    )
        self.assertFalse(is_operation_allowed(principal="api", operation=99))

    def test_failure_status_has_one_mapped_error_detail_and_sanitizes_bad_ids(self) -> None:
        status = build_failure_status(
            grpc_status=grpc.StatusCode.RESOURCE_EXHAUSTED,
            error_code=delivery_pb2.ADMISSION_FULL,
            request_id="10000000-0000-4000-8000-000000000001",
        )

        self.assertEqual(status.code, grpc.StatusCode.RESOURCE_EXHAUSTED.value[0])
        self.assertEqual(len(status.details), 1)
        detail = delivery_pb2.ErrorDetail()
        self.assertTrue(status.details[0].Unpack(detail))
        self.assertEqual(detail.code, delivery_pb2.ADMISSION_FULL)
        self.assertTrue(detail.retryable)
        self.assertEqual(detail.request_id, "10000000-0000-4000-8000-000000000001")
        self.assertLessEqual(len(detail.safe_message.encode("utf-8")), 256)

        invalid_id_status = build_failure_status(
            grpc_status=grpc.StatusCode.INVALID_ARGUMENT,
            error_code=delivery_pb2.REQUEST_LIMIT_EXCEEDED,
            request_id="provider stderr must not escape",
        )
        invalid_id_detail = delivery_pb2.ErrorDetail()
        self.assertTrue(invalid_id_status.details[0].Unpack(invalid_id_detail))
        self.assertEqual(invalid_id_detail.request_id, "")

    def test_failure_policy_matches_the_documented_status_matrix(self) -> None:
        expected_retryability = {
            (grpc.StatusCode.UNAUTHENTICATED, delivery_pb2.CALLER_DENIED): False,
            (grpc.StatusCode.PERMISSION_DENIED, delivery_pb2.CALLER_DENIED): False,
            (grpc.StatusCode.PERMISSION_DENIED, delivery_pb2.OPERATION_DENIED): False,
            (grpc.StatusCode.INVALID_ARGUMENT, delivery_pb2.REQUEST_LIMIT_EXCEEDED): False,
            (grpc.StatusCode.INVALID_ARGUMENT, delivery_pb2.UNKNOWN_ENUM): False,
            (grpc.StatusCode.FAILED_PRECONDITION, delivery_pb2.CONTRACT_MISMATCH): False,
            (grpc.StatusCode.FAILED_PRECONDITION, delivery_pb2.BROKER_NOT_READY): False,
            (grpc.StatusCode.RESOURCE_EXHAUSTED, delivery_pb2.ADMISSION_FULL): True,
            (grpc.StatusCode.DEADLINE_EXCEEDED, delivery_pb2.EXECUTION_TIMEOUT): False,
            (grpc.StatusCode.CANCELLED, delivery_pb2.EXECUTION_TIMEOUT): False,
            (grpc.StatusCode.UNAVAILABLE, delivery_pb2.BROKER_NOT_READY): True,
            (grpc.StatusCode.INTERNAL, delivery_pb2.EXECUTION_FAILED): False,
        }

        self.assertEqual(set(FAILURE_POLICIES), set(expected_retryability))
        for (status_code, error_code), retryable in expected_retryability.items():
            with self.subTest(status=status_code, code=error_code):
                status = build_failure_status(
                    grpc_status=status_code,
                    error_code=error_code,
                    request_id="10000000-0000-4000-8000-000000000001",
                )
                detail = delivery_pb2.ErrorDetail()
                self.assertTrue(status.details[0].Unpack(detail))
                self.assertEqual(detail.retryable, retryable)
                self.assertEqual(detail.retry_after_ms, 0)
                self.assertLessEqual(len(detail.safe_message.encode("utf-8")), 256)

    def test_failure_status_rejects_an_undocumented_status_code_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "not permitted"):
            build_failure_status(
                grpc_status=grpc.StatusCode.OK,
                error_code=delivery_pb2.ADMISSION_FULL,
                request_id="10000000-0000-4000-8000-000000000001",
            )

    def test_generated_result_limits_and_outcomes_are_bounded(self) -> None:
        valid = delivery_pb2.GenerateResult(
            request_id="10000000-0000-4000-8000-000000000001",
            provider_model_id="fixture-model-v1",
            success=delivery_pb2.GenerationSuccess(content="valid generated content"),
        )
        validate_generate_result(valid)

        oversized_content = deepcopy(valid)
        oversized_content.success.content = "x" * (MAX_GENERATED_CONTENT_UTF8_BYTES + 1)
        self._assert_generated_result_violation(
            oversized_content,
            delivery_pb2.TOO_LARGE,
        )

        oversized_result = deepcopy(valid)
        oversized_result.success.content = "x" * MAX_GENERATED_CONTENT_UTF8_BYTES
        oversized_result.provider_model_id = "x" * MAX_RESULT_SERIALIZED_BYTES
        self._assert_generated_result_violation(oversized_result, delivery_pb2.TOO_LARGE)

        missing_outcome = delivery_pb2.GenerateResult(
            request_id="10000000-0000-4000-8000-000000000001"
        )
        malformed_violation = delivery_pb2.GenerateResult(
            request_id="10000000-0000-4000-8000-000000000001",
            invalid_structured_output=delivery_pb2.InvalidStructuredOutput(violation=99),
        )
        for result in (missing_outcome, malformed_violation):
            self._assert_generated_result_violation(result, delivery_pb2.MALFORMED)

    def _assert_rejection(
        self,
        request: delivery_pb2.GenerateRequest,
        error_code: int,
    ) -> None:
        with self.assertRaises(ContractViolation) as raised:
            validate_generate_request(request)
        self.assertEqual(raised.exception.grpc_status, grpc.StatusCode.INVALID_ARGUMENT)
        self.assertEqual(raised.exception.error_code, error_code)
        status = raised.exception.as_rpc_status()
        self.assertIsInstance(status, status_pb2.Status)
        self.assertEqual(len(status.details), 1)

    def _assert_generated_result_violation(
        self,
        result: delivery_pb2.GenerateResult,
        output_violation: int,
    ) -> None:
        with self.assertRaises(GeneratedResultViolation) as raised:
            validate_generate_result(result)
        self.assertEqual(raised.exception.output_violation, output_violation)


def _request_for(operation: int, output_contract: int) -> delivery_pb2.GenerateRequest:
    return delivery_pb2.GenerateRequest(
        request_id="10000000-0000-4000-8000-000000000001",
        correlation_id="synthetic-correlation",
        operation=operation,
        model_id="fixture-model-v1",
        messages=[
            delivery_pb2.ChatMessage(
                role=delivery_pb2.USER,
                content="Summarize the synthetic evidence.",
            )
        ],
        output_contract=output_contract,
    )


def _add_evidence(
    request: delivery_pb2.GenerateRequest,
    *,
    excerpt: str = "Synthetic body-text evidence.",
) -> None:
    index = len(request.evidence_snapshot.candidates)
    request.evidence_snapshot.snapshot_sha256 = b"s" * 32
    request.evidence_snapshot.candidates.add(
        candidate_id=f"candidate-{index}",
        book_id="synthetic-book",
        chunk_id=f"chunk-{index}",
        source_sha256=b"h" * 32,
        scope_fingerprint="scope-v1",
        body_text_eligible=True,
        retrieval_provenance="synthetic-fixture",
        excerpt=excerpt,
        source_revision="r1",
    )
