from __future__ import annotations

import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import (
    AnswerRequest,
    AnswerRuntime,
    EvidenceSnapshot,
    GenerationResult,
    SourceRecord,
    SupportReviewResult,
)


@dataclass
class _Context:
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def remaining_seconds(self) -> float | None:
        return 30.0


class _Retriever:
    def __init__(self, evidence: tuple[EvidenceSnapshot, ...], *, changed: bool = False) -> None:
        self.evidence = evidence
        self.changed = changed

    def retrieve(self, request: AnswerRequest, context: _Context) -> tuple[EvidenceSnapshot, ...]:
        return self.evidence

    def reload_source(self, *, book_id: str, chunk_id: str) -> SourceRecord | None:
        evidence = next(
            (item for item in self.evidence if item.book_id == book_id and item.chunk_id == chunk_id),
            None,
        )
        if evidence is None:
            return None
        return SourceRecord(
            book_id=book_id,
            chunk_id=chunk_id,
            source_revision=("changed" if self.changed else evidence.source_revision),
            text=evidence.excerpt,
        )


class _Broker:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def generate(self, request: object, context: _Context) -> GenerationResult:
        response = self.responses[self.calls]
        self.calls += 1
        return GenerationResult(body=response, provider="fixture", model="fixture-model")


class _Reviewer:
    def __init__(self, supported: bool = True) -> None:
        self.supported = supported
        self.calls = 0

    def review(self, request: object, context: _Context) -> SupportReviewResult:
        self.calls += 1
        return SupportReviewResult(supported=self.supported, reason="fixture")


def _evidence(count: int) -> tuple[EvidenceSnapshot, ...]:
    return tuple(
        EvidenceSnapshot.from_source_record(
            candidate_id=f"S{index}",
            source=SourceRecord(
                book_id="book-1",
                chunk_id=f"chunk-{index}",
                source_revision="revision-1",
                text=f"Fixture evidence passage {index}.",
            ),
            body_text_eligible=True,
        )
        for index in range(1, count + 1)
    )


def _response(answer: str, count: int) -> str:
    return json.dumps({"answer": answer, "sentence_ids": [f"S{index}" for index in range(1, count + 1)]})


class AnswerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def _events(self, runtime: AnswerRuntime, request: AnswerRequest) -> list[object]:
        return [event async for event in runtime.run(request, _Context())]

    async def test_point_bounded_and_broad_paths_have_one_authoritative_result(self) -> None:
        for required in (1, 2, 10):
            with self.subTest(required=required):
                broker = _Broker([_response("A grounded fixture answer.", required)])
                runtime = AnswerRuntime(_Retriever(_evidence(required)), broker, _Reviewer())
                events = await self._events(
                    runtime,
                    AnswerRequest(
                        request_id=f"request-{required}",
                        question="What does the fixture say?",
                        minimum_citation_count=required,
                    ),
                )
                self.assertEqual(
                    [event.event for event in events],
                    ["started", "evidence_candidates", "generation_started", "validation_started", "answer_validated", "completed"],
                )
                validated = events[-2].payload["result"]
                completed = events[-1].payload["result"]
                self.assertIs(validated, completed)
                self.assertEqual(len(completed.citations), required)
                self.assertEqual(broker.calls, 1)

    async def test_insufficient_evidence_and_wrong_scope_refuse_without_generation(self) -> None:
        for evidence in ((), _evidence(1)):
            with self.subTest(evidence=len(evidence)):
                broker = _Broker([])
                runtime = AnswerRuntime(_Retriever(evidence), broker, _Reviewer())
                events = await self._events(
                    runtime,
                    AnswerRequest(
                        request_id=f"refusal-{len(evidence)}",
                        question="What does the fixture say?",
                        minimum_citation_count=2,
                    ),
                )
                self.assertEqual([event.event for event in events], ["started", "evidence_candidates", "completed"])
                self.assertEqual(events[-1].payload["result"].outcome, "insufficient_evidence")
                self.assertEqual(broker.calls, 0)

    async def test_source_change_discards_answer_before_support_review(self) -> None:
        broker = _Broker([_response("A grounded fixture answer.", 1)])
        reviewer = _Reviewer()
        runtime = AnswerRuntime(_Retriever(_evidence(1), changed=True), broker, reviewer)
        events = await self._events(
            runtime,
            AnswerRequest(request_id="changed", question="What happened?"),
        )
        self.assertEqual(
            [event.event for event in events],
            ["started", "evidence_candidates", "generation_started", "validation_started", "completed"],
        )
        self.assertEqual(events[-1].payload["result"].outcome, "source_changed")
        self.assertEqual(reviewer.calls, 0)

    async def test_malformed_output_uses_exactly_one_repair_then_generation_unavailable(self) -> None:
        broker = _Broker(["not JSON", "still not JSON"])
        runtime = AnswerRuntime(_Retriever(_evidence(1)), broker, _Reviewer())
        events = await self._events(
            runtime,
            AnswerRequest(request_id="repair", question="What happened?"),
        )
        self.assertEqual(
            [event.event for event in events],
            [
                "started", "evidence_candidates", "generation_started", "validation_started",
                "generation_started", "validation_started", "completed",
            ],
        )
        self.assertEqual(broker.calls, 2)
        self.assertEqual(events[-1].payload["result"].outcome, "generation_unavailable")

    async def test_malformed_output_repairs_once_and_can_succeed(self) -> None:
        broker = _Broker(["{}", _response("A repaired answer.", 1)])
        runtime = AnswerRuntime(_Retriever(_evidence(1)), broker, _Reviewer())
        events = await self._events(
            runtime,
            AnswerRequest(request_id="repaired", question="What happened?"),
        )
        self.assertEqual(events[-1].payload["result"].outcome, "answered")
        self.assertEqual(broker.calls, 2)
