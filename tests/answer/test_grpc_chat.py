"""Regression coverage for the R2 API-chat generated-client seam."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import (
    AnswerCitation,
    AnswerEvent,
    AnswerRequest,
    AnswerRuntime,
    EvidenceSnapshot,
    GenerationRequest,
    GenerationResult,
    SourceRecord,
    SupportReviewRequest,
)
from librarian_answer_adapters.grpc_broker import GeneratedGrpcBrokerClient
from librarian_answer_adapters.grpc_chat import GrpcChatOperations
from librarian_api.r2_chat import _PhaseRequestContext
from librarian_broker.execution import BrokerScheduler, ProviderExecutor
from librarian_broker.grpc_service import BrokerCredentials, create_broker_server
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import build_stack_contract


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

    async def test_selection_accepts_a_legacy_parent_context_through_the_phase_boundary(self) -> None:
        client = _FakeClient(responses=[json.dumps({"sentence_ids": ["S1"]})])
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        context = _PhaseRequestContext(
            parent=_LegacyContext(), deadline_at=monotonic() + 30
        )

        selected = await operations.select_sources(
            question="Who opens the gate?",
            evidence=(_evidence(),),
            minimum_citation_count=1,
            request_id="10000000-0000-4000-8000-000000000011",
            context=context,
        )

        self.assertEqual(selected, (_evidence(),))
        self.assertEqual(
            [request.operation for request in client.requests],
            [delivery_pb2.SEMANTIC_SOURCE_SELECTION],
        )

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

    async def test_deadline_after_retrieval_completes_without_broker_admission(self) -> None:
        context = _DeadlineContext()
        client = _FakeClient(responses=[])
        operations = GrpcChatOperations(client=client, model_id="gpt-5.6-sol")
        runtime = AnswerRuntime(
            _DeadlineAfterRetrievalRetriever((_evidence(),), context),
            operations.synthesis_broker(),
            operations,
        )

        events = await _collect_events(
            runtime,
            AnswerRequest(
                request_id="10000000-0000-4000-8000-000000000012",
                question="Who opens the gate?",
            ),
            context,
        )

        self.assertEqual([event.event for event in events], ["started", "completed"])
        self.assertEqual(events[-1].payload["result"].outcome, "generation_unavailable")
        self.assertEqual(client.requests, [])

    async def test_deadline_between_synthesis_and_validation_completes_safely(self) -> None:
        context = _DeadlineContext()
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)),
            _DeadlineAfterGenerationBroker(context),
            _UnusedReviewer(),
        )

        events = await _collect_events(
            runtime,
            AnswerRequest(
                request_id="10000000-0000-4000-8000-000000000013",
                question="Who opens the gate?",
            ),
            context,
        )

        self.assertEqual(
            [event.event for event in events],
            ["started", "evidence_candidates", "generation_started", "completed"],
        )
        self.assertEqual(events[-1].payload["result"].outcome, "generation_unavailable")
        self.assertNotIn("cancelled", [event.event for event in events])
        self.assertNotIn("answer_validated", [event.event for event in events])

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


class LiveGrpcChatCancellationTests(unittest.IsolatedAsyncioTestCase):
    """An API cancellation reaches the authenticated generated-stub broker call."""

    async def asyncSetUp(self) -> None:
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"API chat cancellation regression descriptor",
        )
        self.provider = _BlockingApiProvider()
        self.server = create_broker_server(
            contract=self.contract,
            credentials=BrokerCredentials({"api": "api-token"}),
            scheduler=BrokerScheduler(
                self.provider,
                limits=build_broker_execution_limits(validation_reserve_seconds=0.01),
            ),
        )
        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()
        self.client = GeneratedGrpcBrokerClient.connect(
            target=f"127.0.0.1:{port}",
            contract=self.contract,
            principal="api",
            bearer_token="api-token",
        )
        await self.client.ensure_ready()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        await self.server.stop(0)

    async def test_cancelled_api_synthesis_yields_one_terminal_event_and_cancels_rpc(self) -> None:
        context = _DisconnectingContext()
        operations = GrpcChatOperations(client=self.client, model_id="fixture-model")
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)), operations.synthesis_broker(), operations
        )
        collection = asyncio.create_task(
            _collect_events(
                runtime,
                AnswerRequest(
                    request_id="10000000-0000-4000-8000-000000000007",
                    question="Who opens the gate?",
                ),
                context,
            )
        )

        await asyncio.wait_for(self.provider.started.wait(), timeout=1)
        context.cancelled = True
        events = await asyncio.wait_for(collection, timeout=1)
        await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)
        await asyncio.sleep(0)

        self.assertEqual(
            [event.event for event in events],
            ["started", "evidence_candidates", "generation_started", "cancelled"],
        )
        self.assertEqual(
            [event.sequence for event in events], list(range(1, len(events) + 1))
        )
        self.assertEqual(self.provider.operations, [delivery_pb2.GROUNDED_SYNTHESIS])
        self.assertEqual(self.client.principal, "api")
        self.assertNotIn("answer_validated", [event.event for event in events])
        self.assertNotIn("completed", [event.event for event in events])

    async def test_elapsed_api_deadline_is_a_safe_completion_not_a_cancelled_event(self) -> None:
        context = _DeadlineContext()
        operations = GrpcChatOperations(client=self.client, model_id="fixture-model")
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)), operations.synthesis_broker(), operations
        )
        collection = asyncio.create_task(
            _collect_events(
                runtime,
                AnswerRequest(
                    request_id="10000000-0000-4000-8000-000000000008",
                    question="Who opens the gate?",
                ),
                context,
            )
        )

        await asyncio.wait_for(self.provider.started.wait(), timeout=1)
        context.deadline_elapsed = True
        events = await asyncio.wait_for(collection, timeout=1)
        await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)

        self.assertEqual(
            [event.event for event in events],
            ["started", "evidence_candidates", "generation_started", "completed"],
        )
        result = events[-1].payload["result"]
        self.assertEqual(result.outcome, "generation_unavailable")
        self.assertNotIn("cancelled", [event.event for event in events])
        self.assertNotIn("answer_validated", [event.event for event in events])

    async def test_explicit_api_cancellation_is_a_cancelled_terminal_event(self) -> None:
        context = _ExplicitCancellationContext()
        operations = GrpcChatOperations(client=self.client, model_id="fixture-model")
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)), operations.synthesis_broker(), operations
        )
        collection = asyncio.create_task(
            _collect_events(
                runtime,
                AnswerRequest(
                    request_id="10000000-0000-4000-8000-000000000009",
                    question="Who opens the gate?",
                ),
                context,
            )
        )

        await asyncio.wait_for(self.provider.started.wait(), timeout=1)
        context.cancelled = True
        events = await asyncio.wait_for(collection, timeout=1)
        await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)

        self.assertEqual(
            [event.event for event in events],
            ["started", "evidence_candidates", "generation_started", "cancelled"],
        )
        self.assertNotIn("answer_validated", [event.event for event in events])
        self.assertNotIn("completed", [event.event for event in events])

    async def test_unrelated_task_cancellation_propagates_without_terminal_event(self) -> None:
        context = _Context()
        operations = GrpcChatOperations(client=self.client, model_id="fixture-model")
        runtime = AnswerRuntime(
            _Retriever((_evidence(),)), operations.synthesis_broker(), operations
        )
        collection = asyncio.create_task(
            _collect_events(
                runtime,
                AnswerRequest(
                    request_id="10000000-0000-4000-8000-000000000010",
                    question="Who opens the gate?",
                ),
                context,
            )
        )

        await asyncio.wait_for(self.provider.started.wait(), timeout=1)
        collection.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await collection
        await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)


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


class _BlockingApiProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.operations: list[int] = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def generate(self, request, *, timeout_seconds: float) -> tuple[str, str]:
        del timeout_seconds
        self.operations.append(request.operation)
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class _Context:
    def __init__(self) -> None:
        self.cancelled = False
        self.was_disconnected = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def cancellation_cause(self) -> str | None:
        return "explicit" if self.cancelled else None

    def remaining_seconds(self) -> float:
        return 30.0


class _LegacyContext:
    """Pre-cancellation-cause context retained by the narrow port fallback."""

    def is_cancelled(self) -> bool:
        return False

    def remaining_seconds(self) -> float:
        return 30.0


class _DisconnectingContext(_Context):
    def __init__(self) -> None:
        super().__init__()
        self.was_disconnected = True

    def remaining_seconds(self) -> float:
        return 0.0 if self.cancelled else 30.0

    def cancellation_cause(self) -> str | None:
        return "disconnect" if self.cancelled else None


class _ExplicitCancellationContext(_Context):
    def remaining_seconds(self) -> float:
        return 0.0 if self.cancelled else 30.0


class _DeadlineContext(_Context):
    def __init__(self) -> None:
        super().__init__()
        self.deadline_elapsed = False

    def is_cancelled(self) -> bool:
        return self.deadline_elapsed

    def cancellation_cause(self) -> str | None:
        return "deadline" if self.deadline_elapsed else None

    def remaining_seconds(self) -> float:
        return 0.0 if self.deadline_elapsed else 30.0


class _DeadlineAfterRetrievalRetriever:
    def __init__(
        self, evidence: tuple[EvidenceSnapshot, ...], context: _DeadlineContext
    ) -> None:
        self.evidence = evidence
        self.context = context

    def retrieve(self, request, context) -> tuple[EvidenceSnapshot, ...]:
        del request, context
        self.context.deadline_elapsed = True
        return self.evidence


class _DeadlineAfterGenerationBroker:
    def __init__(self, context: _DeadlineContext) -> None:
        self.context = context

    def generate(self, request, context) -> GenerationResult:
        del request, context
        self.context.deadline_elapsed = True
        return GenerationResult(
            body=json.dumps({"answer": "Mara opens the gate.", "sentence_ids": ["S1"]}),
            provider="fixture",
            model="fixture-model",
        )


class _UnusedReviewer:
    def review(self, request, context):
        raise AssertionError("a deadline before validation must not reach support review")


async def _collect_events(
    runtime: AnswerRuntime, request: AnswerRequest, context: _Context
) -> list[AnswerEvent]:
    return [event async for event in runtime.run(request, context)]


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
