"""Regression coverage for the R2 API-chat generated-client seam."""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import (
    AnswerCitation,
    AnswerRequest,
    AnswerRuntime,
    EvidenceSnapshot,
    GenerationRequest,
    SourceRecord,
    SupportReviewRequest,
)
from librarian_answer_adapters.grpc_chat import GrpcChatOperations
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)


class GrpcChatOperationsTests(unittest.IsolatedAsyncioTestCase):
    """The API seam uses generated operations only and fails closed on review."""

    async def test_selection_synthesis_and_review_use_the_one_generated_client(self) -> None:
        client = _FakeClient(
            responses=[
                json.dumps({"sentence_ids": ["S1"]}),
                json.dumps({"answer": "Mara opens the gate.", "sentence_ids": ["S1"]}),
                json.dumps(
                    {
                        "evidence_verdict": "supported",
                        "citation_relevance": "all_relevant",
                        "missing_coverage": [],
                        "unsupported_claims": [],
                        "reason": "The cited evidence supports the answer.",
                    }
                ),
            ]
        )
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        context = _Context()
        evidence = (_evidence(),)

        selected = await operations.select_sources(
            question="Who opens the gate?",
            evidence=evidence,
            minimum_citation_count=1,
            request_id="10000000-0000-4000-8000-000000000001",
            context=context,
        )
        synthesis = await operations.synthesis_broker().generate(
            GenerationRequest(
                operation="GROUNDED_SYNTHESIS",
                messages=(),
                request_id="10000000-0000-4000-8000-000000000002",
                evidence_snapshot=evidence,
            ),
            context,
        )
        review = await operations.review(
            SupportReviewRequest(
                request_id="10000000-0000-4000-8000-000000000003",
                question="Who opens the gate?",
                answer="Mara opens the gate.",
                citations=(AnswerCitation("S1", "book", "chunk"),),
                evidence_snapshot=evidence,
            ),
            context,
        )

        self.assertEqual(selected, evidence)
        self.assertEqual(json.loads(synthesis.body)["answer"], "Mara opens the gate.")
        self.assertTrue(review.supported)
        self.assertEqual(
            [request.operation for request in client.requests],
            [
                delivery_pb2.SEMANTIC_SOURCE_SELECTION,
                delivery_pb2.GROUNDED_SYNTHESIS,
                delivery_pb2.SUPPORT_REVIEW,
            ],
        )
        self.assertTrue(all(request.evidence_snapshot.candidates for request in client.requests))

    async def test_invalid_selection_or_review_is_never_treated_as_supported(self) -> None:
        client = _FakeClient(
            responses=[
                json.dumps({"sentence_ids": ["unknown"]}),
                "not JSON",
            ]
        )
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        evidence = (_evidence(),)
        context = _Context()

        selection = await operations.select_sources(
            question="Who opens the gate?",
            evidence=evidence,
            minimum_citation_count=1,
            request_id="10000000-0000-4000-8000-000000000001",
            context=context,
        )
        review = await operations.review(
            SupportReviewRequest(
                request_id="10000000-0000-4000-8000-000000000003",
                question="Who opens the gate?",
                answer="Mara opens the gate.",
                citations=(AnswerCitation("S1", "book", "chunk"),),
                evidence_snapshot=evidence,
            ),
            context,
        )

        self.assertIsNone(selection)
        self.assertFalse(review.supported)
        self.assertEqual(review.reason, "invalid_support_review")

    async def test_list_shaped_json_never_raises_or_passes_validation(self) -> None:
        client = _FakeClient(
            responses=[
                json.dumps(["sentence_ids"]),
                json.dumps(
                    [
                        "evidence_verdict",
                        "citation_relevance",
                        "missing_coverage",
                        "unsupported_claims",
                        "reason",
                    ]
                ),
            ]
        )
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        evidence = (_evidence(),)

        selection = await operations.select_sources(
            question="Who opens the gate?",
            evidence=evidence,
            minimum_citation_count=1,
            request_id="10000000-0000-4000-8000-000000000001",
            context=_Context(),
        )
        review = await operations.review(
            SupportReviewRequest(
                request_id="10000000-0000-4000-8000-000000000003",
                question="Who opens the gate?",
                answer="Mara opens the gate.",
                citations=(AnswerCitation("S1", "book", "chunk"),),
                evidence_snapshot=evidence,
            ),
            _Context(),
        )

        self.assertIsNone(selection)
        self.assertFalse(review.supported)
        self.assertEqual(review.reason, "invalid_support_review")

    async def test_answer_runtime_awaits_the_grpc_reviewer_before_accepting(self) -> None:
        client = _FakeClient(
            responses=[
                json.dumps({"answer": "Mara opens the gate.", "sentence_ids": ["S1"]}),
                _review_payload(supported=True),
            ]
        )
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        evidence = (_evidence(),)
        runtime = AnswerRuntime(
            _Retriever(evidence), operations.synthesis_broker(), operations
        )

        result = await runtime.collect(
            AnswerRequest(
                request_id="10000000-0000-4000-8000-000000000004",
                question="Who opens the gate?",
            ),
            _Context(),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.outcome, "answered")
        self.assertEqual(
            [request.operation for request in client.requests],
            [delivery_pb2.GROUNDED_SYNTHESIS, delivery_pb2.SUPPORT_REVIEW],
        )
        self.assertEqual(client.requests[-1].request_id, result.request_id)

    async def test_rejected_grpc_review_consumes_one_repair_then_rechecks_support(self) -> None:
        client = _FakeClient(
            responses=[
                json.dumps({"answer": "Mara opens the gate.", "sentence_ids": ["S1"]}),
                _review_payload(supported=False),
                json.dumps({"answer": "Mara opens the gate.", "sentence_ids": ["S1"]}),
                _review_payload(supported=True),
            ]
        )
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)), operations.synthesis_broker(), operations
        )

        result = await runtime.collect(
            AnswerRequest(
                request_id="10000000-0000-4000-8000-000000000005",
                question="Who opens the gate?",
            ),
            _Context(),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.outcome, "answered")
        self.assertEqual(
            [request.operation for request in client.requests],
            [
                delivery_pb2.GROUNDED_SYNTHESIS,
                delivery_pb2.SUPPORT_REVIEW,
                delivery_pb2.GROUNDED_SYNTHESIS,
                delivery_pb2.SUPPORT_REVIEW,
            ],
        )

    async def test_cancellation_during_grpc_review_has_no_late_answer(self) -> None:
        client = _FakeClient(
            responses=[
                json.dumps({"answer": "Mara opens the gate.", "sentence_ids": ["S1"]}),
                _review_payload(supported=True),
            ]
        )
        context = _Context()
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)),
            operations.synthesis_broker(),
            _CancellingReviewer(operations, context),
        )

        events = [
            event
            async for event in runtime.run(
                AnswerRequest(
                    request_id="10000000-0000-4000-8000-000000000006",
                    question="Who opens the gate?",
                ),
                context,
            )
        ]

        self.assertEqual(events[-1].event, "cancelled")
        self.assertNotIn("answer_validated", [event.event for event in events])


@dataclass
class _FakeClient:
    responses: list[str]
    requests: list[delivery_pb2.GenerateRequest] = field(default_factory=list)

    async def generate(self, request, *, timeout):
        self.requests.append(request)
        return delivery_pb2.GenerateResult(
            request_id=request.request_id,
            provider_model_id="fixture-model",
            success=delivery_pb2.GenerationSuccess(content=self.responses.pop(0)),
        )


class _Context:
    def __init__(self) -> None:
        self.cancelled = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def remaining_seconds(self) -> float:
        return 30.0


class _CancellingReviewer:
    def __init__(self, operations: GrpcChatOperations, context: _Context) -> None:
        self.operations = operations
        self.context = context

    async def review(self, request, context):
        result = await self.operations.review(request, context)
        self.context.cancelled = True
        return result


class _Retriever:
    def __init__(self, evidence: tuple[EvidenceSnapshot, ...]) -> None:
        self.evidence = evidence

    def retrieve(self, request, context) -> tuple[EvidenceSnapshot, ...]:
        return self.evidence

    def reload_source(self, *, book_id: str, chunk_id: str) -> SourceRecord | None:
        for item in self.evidence:
            if item.book_id == book_id and item.chunk_id == chunk_id:
                return SourceRecord(
                    book_id=item.book_id,
                    chunk_id=item.chunk_id,
                    source_revision=item.source_revision,
                    text=item.excerpt,
                )
        return None


def _evidence() -> EvidenceSnapshot:
    return EvidenceSnapshot.from_source_record(
        candidate_id="S1",
        source=SourceRecord(
            book_id="book",
            chunk_id="chunk",
            source_revision="revision",
            text="Mara opens the gate.",
        ),
        body_text_eligible=True,
        excerpt="Mara opens the gate.",
    )


def _review_payload(*, supported: bool) -> str:
    return json.dumps(
        {
            "evidence_verdict": "supported" if supported else "insufficient",
            "citation_relevance": "all_relevant",
            "missing_coverage": [] if supported else ["The answer needs a clearer connection."],
            "unsupported_claims": [],
            "reason": "fixture review",
        }
    )
