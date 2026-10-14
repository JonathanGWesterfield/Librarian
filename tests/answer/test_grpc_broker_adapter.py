"""Tests for the generated-stub answer-runtime broker adapter."""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

import grpc

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import (
    EvidenceSnapshot,
    GenerationMessage,
    GenerationRequest,
    SourceRecord,
)
from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
    GrpcRuntimeGenerationBroker,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import build_stack_contract


class GrpcRuntimeGenerationBrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _FakeClient()
        self.request = GenerationRequest(
            operation="GROUNDED_SYNTHESIS",
            request_id="10000000-0000-4000-8000-000000000001",
            messages=(GenerationMessage(role="user", content="Use the evidence."),),
            evidence_snapshot=(_snapshot(),),
        )

    def test_grounded_synthesis_selection_and_review_use_v1_generated_requests(self) -> None:
        cases = (
            (delivery_pb2.GROUNDED_SYNTHESIS, delivery_pb2.GROUNDED_ANSWER_JSON_V1),
            (delivery_pb2.SEMANTIC_SOURCE_SELECTION, delivery_pb2.SOURCE_SELECTION_JSON_V1),
            (delivery_pb2.SUPPORT_REVIEW, delivery_pb2.SUPPORT_REVIEW_JSON_V1),
        )
        for operation, output_contract in cases:
            with self.subTest(operation=operation):
                adapter = GrpcRuntimeGenerationBroker(
                    client=self.client,
                    operation=operation,
                    output_contract=output_contract,
                    model_id="gpt-5.6-sol",
                )
                result = adapter.generate(self.request, _Context())

                self.assertEqual(result.body, "Fixture generated output.")
                proto = self.client.requests[-1]
                self.assertEqual(proto.operation, operation)
                self.assertEqual(proto.output_contract, output_contract)
                self.assertEqual(proto.request_id, self.request.request_id)
                self.assertEqual(proto.correlation_id, self.request.request_id)
                self.assertEqual(len(proto.evidence_snapshot.candidates), 1)
                self.assertEqual(
                    proto.evidence_snapshot.candidates[0].candidate_id, "S1:1"
                )
                self.assertEqual(len(proto.evidence_snapshot.snapshot_sha256), 32)

    def test_invalid_structured_output_consumes_the_runtime_repair_budget(self) -> None:
        self.client.result = delivery_pb2.GenerateResult(
            request_id=self.request.request_id,
            provider_model_id="fixture-model",
            invalid_structured_output=delivery_pb2.InvalidStructuredOutput(
                violation=delivery_pb2.MALFORMED
            ),
        )
        adapter = GrpcRuntimeGenerationBroker(
            client=self.client,
            operation=delivery_pb2.GROUNDED_SYNTHESIS,
            output_contract=delivery_pb2.GROUNDED_ANSWER_JSON_V1,
            model_id="gpt-5.6-sol",
        )

        result = adapter.generate(self.request, _Context())

        self.assertEqual(result.body, "{}")
        self.assertTrue(result.repairable)
        self.assertEqual(result.repair_hint, "invalid_structured_output")

    def test_generated_client_never_executes_before_a_capability_handshake(self) -> None:
        contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"adapter fixture descriptor",
        )
        channel = grpc.insecure_channel("dns:///codex-broker:50051")
        self.addCleanup(channel.close)
        client = GeneratedGrpcBrokerClient(
            channel=channel,
            contract=contract,
            principal="api",
            bearer_token="fixture-token",
        )

        with self.assertRaises(GrpcBrokerClientError) as raised:
            client.generate(delivery_pb2.GenerateRequest())

        self.assertEqual(raised.exception.status, grpc.StatusCode.FAILED_PRECONDITION)
        self.assertEqual(raised.exception.error_code, delivery_pb2.CONTRACT_MISMATCH)


@dataclass
class _FakeClient:
    requests: list[delivery_pb2.GenerateRequest] | None = None
    result: delivery_pb2.GenerateResult | None = None

    def __post_init__(self) -> None:
        self.requests = []
        if self.result is None:
            self.result = delivery_pb2.GenerateResult(
                request_id="10000000-0000-4000-8000-000000000001",
                provider_model_id="fixture-model",
                success=delivery_pb2.GenerationSuccess(content="Fixture generated output."),
            )

    def generate(self, request, *, timeout):
        assert self.requests is not None
        assert self.result is not None
        self.requests.append(request)
        return self.result


class _Context:
    def is_cancelled(self) -> bool:
        return False

    def remaining_seconds(self) -> float:
        return 10


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot.from_source_record(
        candidate_id="S1:1",
        source=SourceRecord(
            book_id="fixture-book",
            chunk_id="fixture-chunk",
            source_revision="fixture-revision",
            text="Fixture body evidence.",
        ),
        effective_scope={"book_id": "fixture-book"},
        body_text_eligible=True,
        retrieval_provenance={"backend": "fixture"},
        excerpt="Fixture body evidence.",
    )
