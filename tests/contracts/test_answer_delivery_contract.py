"""Regression tests for the canonical answer-delivery protobuf contract."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

from google.protobuf import descriptor_pb2


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2_grpc as delivery_grpc,
)


class AnswerDeliveryContractTests(unittest.TestCase):
    """Keep field numbers and service behavior stable before transport work begins."""

    def test_descriptor_defines_the_single_v1_broker_execution_rpc(self) -> None:
        descriptor = _file_descriptor_proto()

        self.assertEqual(descriptor.name, "librarian/answer/v1/answer_delivery.proto")
        self.assertEqual(descriptor.package, "librarian.answer.v1")
        self.assertEqual(descriptor.dependency, [])
        self.assertEqual([service.name for service in descriptor.service], ["GenerationBroker"])
        self.assertEqual(
            [method.name for method in descriptor.service[0].method],
            ["GetCapabilities", "Generate"],
        )
        self.assertEqual(
            [
                (method.input_type, method.output_type, method.client_streaming, method.server_streaming)
                for method in descriptor.service[0].method
            ],
            [
                (
                    ".librarian.answer.v1.CapabilitiesRequest",
                    ".librarian.answer.v1.Capabilities",
                    False,
                    False,
                ),
                (
                    ".librarian.answer.v1.GenerateRequest",
                    ".librarian.answer.v1.GenerateResult",
                    False,
                    False,
                ),
            ],
        )
        self.assertTrue(hasattr(delivery_grpc, "GenerationBrokerStub"))
        self.assertTrue(hasattr(delivery_grpc, "add_GenerationBrokerServicer_to_server"))

    def test_contract_field_numbers_and_reserved_ranges_are_stable(self) -> None:
        descriptor = _file_descriptor_proto()
        messages = {message.name: message for message in descriptor.message_type}

        expected_messages = {
            "CapabilitiesRequest": (
                ["contract_major", "contract_minor", "descriptor_sha256", "stack_release_sha"],
                [(5, 16)],
            ),
            "Capabilities": (
                [
                    "contract_major",
                    "min_contract_minor",
                    "max_contract_minor",
                    "descriptor_sha256",
                    "stack_release_sha",
                    "operations",
                ],
                [(7, 16)],
            ),
            "ChatMessage": (["role", "content"], [(3, 16)]),
            "EvidenceCandidate": (
                [
                    "candidate_id",
                    "book_id",
                    "chunk_id",
                    "source_sha256",
                    "scope_fingerprint",
                    "body_text_eligible",
                    "retrieval_provenance",
                    "excerpt",
                    "source_revision",
                ],
                [(10, 16)],
            ),
            "EvidenceSnapshot": (["candidates", "snapshot_sha256"], [(3, 16)]),
            "GenerateRequest": (
                [
                    "request_id",
                    "correlation_id",
                    "operation",
                    "model_id",
                    "messages",
                    "output_contract",
                    "evidence_snapshot",
                ],
                [(8, 16)],
            ),
            "GenerationSuccess": (["content"], [(2, 16)]),
            "InvalidStructuredOutput": (["violation"], [(2, 16)]),
            "GenerateResult": (
                [
                    "request_id",
                    "provider_model_id",
                    "queue_wait_ms",
                    "execution_ms",
                    "success",
                    "invalid_structured_output",
                ],
                [(7, 16)],
            ),
            "ErrorDetail": (
                ["code", "retryable", "retry_after_ms", "safe_message", "request_id"],
                [(6, 16)],
            ),
        }

        self.assertEqual(set(messages), set(expected_messages))
        for message_name, (field_names, reserved_ranges) in expected_messages.items():
            message = messages[message_name]
            self.assertEqual(
                [(field.name, field.number) for field in message.field],
                [(field_name, number) for number, field_name in enumerate(field_names, start=1)],
            )
            self.assertEqual(_reserved_ranges(message), reserved_ranges)

        self.assertEqual(
            [field.name for field in messages["GenerateResult"].field if field.HasField("oneof_index")],
            ["success", "invalid_structured_output"],
        )

    def test_operation_and_output_contract_enums_match_the_v1_matrix(self) -> None:
        expected_enums = {
            "GenerationOperation": {
                "GROUNDED_SYNTHESIS": 1,
                "SEMANTIC_SOURCE_SELECTION": 2,
                "SUPPORT_REVIEW": 3,
                "EVALUATOR_JUDGEMENT": 4,
                "CHAPTER_SUMMARIZATION": 5,
                "BOOK_SUMMARIZATION": 6,
                "TAG_GENERATION": 7,
                "GENRE_GENERATION": 8,
                "RECOMMENDATION_SYNTHESIS": 9,
            },
            "OutputContract": {
                "GROUNDED_ANSWER_JSON_V1": 1,
                "SOURCE_SELECTION_JSON_V1": 2,
                "SUPPORT_REVIEW_JSON_V1": 3,
                "EVALUATOR_VERDICT_JSON_V1": 4,
                "PLAIN_TEXT_V1": 5,
                "TAGS_JSON_V1": 6,
                "GENRES_JSON_V1": 7,
            },
            "MessageRole": {"SYSTEM": 1, "USER": 2, "ASSISTANT": 3},
            "OutputViolation": {"MALFORMED": 1, "TOO_LARGE": 2},
            "ErrorCode": {
                "REQUEST_LIMIT_EXCEEDED": 1,
                "UNKNOWN_ENUM": 2,
                "CONTRACT_MISMATCH": 3,
                "CALLER_DENIED": 4,
                "OPERATION_DENIED": 5,
                "BROKER_NOT_READY": 6,
                "ADMISSION_FULL": 7,
                "EXECUTION_TIMEOUT": 8,
                "EXECUTION_FAILED": 9,
            },
        }
        descriptor = _file_descriptor_proto()
        enums = {enum.name: enum for enum in descriptor.enum_type}

        self.assertEqual(set(enums), set(expected_enums))
        for enum_name, expected_values in expected_enums.items():
            enum = enums[enum_name]
            self.assertEqual(
                [(value.name, value.number) for value in enum.value if value.number],
                list(expected_values.items()),
            )
            generated_enum = getattr(delivery_pb2, enum_name)
            self.assertEqual(
                {name: value for name, value in generated_enum.items() if value},
                expected_values,
            )

        self.assertEqual(_enum_reserved_ranges(enums["GenerationOperation"]), [(10, 15)])
        self.assertEqual(_enum_reserved_ranges(enums["OutputContract"]), [(8, 15)])
        self.assertEqual(_enum_reserved_ranges(enums["MessageRole"]), [])
        self.assertEqual(_enum_reserved_ranges(enums["OutputViolation"]), [])
        self.assertEqual(_enum_reserved_ranges(enums["ErrorCode"]), [])

    def test_checked_in_descriptor_matches_the_generated_module(self) -> None:
        descriptor_path = REPO_ROOT / "proto/librarian/answer/v1/answer_delivery.pb"
        descriptor_set = descriptor_pb2.FileDescriptorSet()
        descriptor_set.ParseFromString(descriptor_path.read_bytes())

        self.assertEqual(len(descriptor_set.file), 1)
        descriptor = descriptor_set.file[0]
        _clear_default_json_names(descriptor)
        self.assertEqual(
            descriptor.SerializeToString(deterministic=True), delivery_pb2.DESCRIPTOR.serialized_pb
        )

    def test_generation_check_detects_no_contract_drift(self) -> None:
        completed = subprocess.run(
            [str(REPO_ROOT / "scripts/generate_contracts.sh"), "--check"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


def _file_descriptor_proto() -> descriptor_pb2.FileDescriptorProto:
    descriptor = descriptor_pb2.FileDescriptorProto()
    descriptor.ParseFromString(delivery_pb2.DESCRIPTOR.serialized_pb)
    return descriptor


def _reserved_ranges(message: descriptor_pb2.DescriptorProto) -> list[tuple[int, int]]:
    return [(item.start, item.end) for item in message.reserved_range]


def _enum_reserved_ranges(enum: descriptor_pb2.EnumDescriptorProto) -> list[tuple[int, int]]:
    return [(item.start, item.end) for item in enum.reserved_range]


def _clear_default_json_names(descriptor: descriptor_pb2.FileDescriptorProto) -> None:
    """Normalize protoc's descriptor-set-only default JSON-name expansion."""

    for message in descriptor.message_type:
        for field in message.field:
            field.ClearField("json_name")
