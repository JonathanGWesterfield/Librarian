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

    async def test_deterministic_legacy_terminal_parity_matrix(self) -> None:
        """R1 terminal rules and the extracted runtime agree for every M02 case.

        ``_legacy_terminal_baseline`` is intentionally small and independent
        of ``AnswerRuntime``.  It records the R1 buffered terminal contract
        before lifecycle/event assembly: an evidence floor refusal never calls
        generation; malformed output gets one repair; and an otherwise valid
        answer is discarded when its source changes.
        """

        cases = (
            ("point", 1, _evidence(1), [_response("Point answer.", 1)], False),
            ("bounded", 2, _evidence(2), [_response("Bounded answer.", 2)], False),
            ("broad", 10, _evidence(10), [_response("Broad answer.", 10)], False),
            ("refusal", 2, _evidence(1), [], False),
            ("wrong_scope", 1, (), [], False),
            ("source_changed", 1, _evidence(1), [_response("Changed answer.", 1)], True),
            ("repair", 1, _evidence(1), ["{}", _response("Repaired answer.", 1)], False),
        )
        for name, required, evidence, responses, changed in cases:
            with self.subTest(case=name):
                expected = _legacy_terminal_baseline(
                    evidence=evidence,
                    required=required,
                    responses=list(responses),
                    source_changed=changed,
                )
                broker = _Broker(list(responses))
                runtime = AnswerRuntime(
                    _Retriever(evidence, changed=changed), broker, _Reviewer()
                )
                events = await self._events(
                    runtime,
                    AnswerRequest(
                        request_id=f"parity-{name}",
                        question="What does the fixture say?",
                        minimum_citation_count=required,
                    ),
                )
                result = events[-1].payload.get("result")
                self.assertEqual(result.outcome, expected["outcome"])
                self.assertEqual(result.answer, expected["answer"])
                self.assertEqual(
                    tuple((item.candidate_id, item.book_id, item.chunk_id) for item in result.citations),
                    expected["citations"],
                )
                self.assertEqual(broker.calls, expected["generation_calls"])


def _legacy_terminal_baseline(
    *,
    evidence: tuple[EvidenceSnapshot, ...],
    required: int,
    responses: list[str],
    source_changed: bool,
) -> dict[str, object]:
    """Deterministic R1 buffered-result baseline for M02 parity coverage."""

    eligible = tuple(item for item in evidence if item.body_text_eligible)
    if len({item.chunk_id for item in eligible}) < required:
        return {"outcome": "insufficient_evidence", "answer": "I could not find enough relevant body-text evidence to answer that reliably.", "citations": (), "generation_calls": 0}
    calls = 0
    for _attempt in range(2):
        calls += 1
        try:
            payload = json.loads(responses.pop(0))
        except (IndexError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict) or set(payload) != {"answer", "sentence_ids"}:
            continue
        answer = payload.get("answer")
        selected_ids = payload.get("sentence_ids")
        candidates = {item.candidate_id: item for item in eligible}
        if (
            not isinstance(answer, str)
            or not isinstance(selected_ids, list)
            or len(selected_ids) != len(set(selected_ids))
            or any(not isinstance(item, str) or item not in candidates for item in selected_ids)
        ):
            continue
        selected = tuple(candidates[item] for item in selected_ids)
        if len({item.chunk_id for item in selected}) < required:
            continue
        if source_changed:
            return {"outcome": "source_changed", "answer": "The source text changed while I was checking this answer. Please try again.", "citations": (), "generation_calls": calls}
        return {
            "outcome": "answered",
            "answer": answer,
            "citations": tuple((item.candidate_id, item.book_id, item.chunk_id) for item in selected),
            "generation_calls": calls,
        }
    return {"outcome": "generation_unavailable", "answer": "I could not produce a reliably grounded answer.", "citations": (), "generation_calls": calls}
