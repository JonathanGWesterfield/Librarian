"""The in-process, transport-independent grounded-answer runtime.

This module deliberately knows only the immutable answer values and the four
runtime ports.  It is therefore usable by today's chat facade and by the future
gRPC/SSE adapters without allowing either transport to own grounding policy.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

from librarian_answer.models import (
    ANSWER_EVENT_SCHEMA_VERSION,
    AnswerCitation,
    AnswerEvent,
    AnswerRequest,
    AnswerResult,
    EvidenceSnapshot,
    GenerationMessage,
    GenerationRequest,
    SupportReviewRequest,
)
from librarian_answer.ports import (
    EvidenceRetriever,
    GenerationBroker,
    RequestContext,
    SupportReviewer,
)
from librarian_answer.snapshots import SourceFreshness, reload_citation_sources

_MAX_REPAIR_ATTEMPTS = 1
_SAFE_GENERATION_FAILURE = "I could not produce a reliably grounded answer."
_SAFE_INSUFFICIENT_EVIDENCE = (
    "I could not find enough relevant body-text evidence to answer that reliably."
)
_SAFE_SOURCE_CHANGED = (
    "The source text changed while I was checking this answer. Please try again."
)


@dataclass(frozen=True)
class AnswerRuntime:
    """Assemble one authoritative result and a monotonic event lifecycle."""

    evidence_retriever: EvidenceRetriever
    generation_broker: GenerationBroker
    support_reviewer: SupportReviewer

    async def run(
        self, request: AnswerRequest, context: RequestContext
    ) -> AsyncIterator[AnswerEvent]:
        """Run one grounded answer without exposing an unvalidated draft.

        Every completed answer shares the exact ``AnswerResult`` value with its
        preceding ``answer_validated`` event.  Refusals and safe failures have
        a completed terminal event only.  The implementation is an async
        iterator now, even though the R1 ports are synchronous, so the public
        lifecycle is identical when a later adapter becomes asynchronous.
        """

        sequence = 0

        def event(name: str, payload: Mapping[str, object] | None = None) -> AnswerEvent:
            nonlocal sequence
            sequence += 1
            return AnswerEvent(
                schema_version=ANSWER_EVENT_SCHEMA_VERSION,
                request_id=request.request_id,
                sequence=sequence,
                event=name,
                payload=payload or {},
            )

        yield event("started")
        if context.is_cancelled():
            yield event("cancelled")
            return

        try:
            evidence = self.evidence_retriever.retrieve(request, context)
        except Exception:  # noqa: BLE001 - port failures are intentionally made safe.
            yield event("failed", {"error": "evidence retrieval failed"})
            return

        if context.is_cancelled():
            yield event("cancelled")
            return

        yield event("evidence_candidates", _candidate_payload(evidence))
        required_sources = request.minimum_citation_count
        eligible = _eligible_evidence(evidence)
        if not _has_required_distinct_sources(eligible, required_sources):
            result = _result(
                request, "insufficient_evidence", _SAFE_INSUFFICIENT_EVIDENCE
            )
            yield event("completed", {"result": result})
            return

        for attempt in range(1, _MAX_REPAIR_ATTEMPTS + 2):
            if context.is_cancelled():
                yield event("cancelled")
                return
            yield event("generation_started", {"attempt": attempt})
            try:
                generated = self.generation_broker.generate(
                    GenerationRequest(
                        operation="GROUNDED_SYNTHESIS",
                        messages=_synthesis_messages(
                            request.question, eligible, repair=attempt > 1
                        ),
                        response_format="grounded_chat_synthesis",
                    ),
                    context,
                )
            except Exception:  # noqa: BLE001 - provider failures must not leak a draft.
                result = _result(
                    request, "generation_unavailable", _SAFE_GENERATION_FAILURE
                )
                yield event("completed", {"result": result})
                return

            if context.is_cancelled():
                yield event("cancelled")
                return
            yield event("validation_started", {"attempt": attempt})
            candidate = _validated_candidate(
                generated.body,
                evidence=eligible,
                required_sources=required_sources,
            )
            if candidate is None:
                if attempt <= _MAX_REPAIR_ATTEMPTS:
                    continue
                result = _result(
                    request, "generation_unavailable", _SAFE_GENERATION_FAILURE
                )
                yield event("completed", {"result": result})
                return

            answer, citations, citation_evidence = candidate
            freshness = reload_citation_sources(
                citation_evidence,
                lambda book_id, chunk_id: self.evidence_retriever.reload_source(
                    book_id=book_id, chunk_id=chunk_id
                ),
            )
            if freshness is SourceFreshness.SOURCE_CHANGED:
                result = _result(request, "source_changed", _SAFE_SOURCE_CHANGED)
                yield event("completed", {"result": result})
                return
            try:
                review = self.support_reviewer.review(
                    SupportReviewRequest(
                        question=request.question,
                        answer=answer,
                        citations=citations,
                        evidence_snapshot=citation_evidence,
                    ),
                    context,
                )
            except Exception:  # noqa: BLE001 - a review failure consumes the repair budget.
                review = None
            if review is None or not review.supported:
                if attempt <= _MAX_REPAIR_ATTEMPTS:
                    continue
                result = _result(
                    request, "generation_unavailable", _SAFE_GENERATION_FAILURE
                )
                yield event("completed", {"result": result})
                return

            result = _result(request, "answered", answer, citations)
            yield event("answer_validated", {"result": result})
            yield event("completed", {"result": result})
            return

    async def collect(self, request: AnswerRequest, context: RequestContext) -> AnswerResult | None:
        """Collect the same lifecycle used by buffered delivery adapters."""

        terminal: AnswerResult | None = None
        async for answer_event in self.run(request, context):
            if answer_event.event == "completed":
                value = answer_event.payload.get("result")
                if isinstance(value, AnswerResult):
                    terminal = value
        return terminal


def _eligible_evidence(
    evidence: Sequence[EvidenceSnapshot],
) -> tuple[EvidenceSnapshot, ...]:
    return tuple(item for item in evidence if item.body_text_eligible)


def _has_required_distinct_sources(
    evidence: Sequence[EvidenceSnapshot], required_sources: int
) -> bool:
    return len({item.chunk_id for item in evidence}) >= required_sources


def _candidate_payload(evidence: Sequence[EvidenceSnapshot]) -> dict[str, object]:
    """Expose only the progress metadata permitted by the domain design."""

    return {
        "candidate_count": len(evidence),
        "candidates": tuple(
            {
                "candidate_id": item.candidate_id,
                "book_id": item.book_id,
                "book_title": item.book_title,
            }
            for item in evidence
        ),
    }


def _synthesis_messages(
    question: str, evidence: Sequence[EvidenceSnapshot], *, repair: bool
) -> tuple[GenerationMessage, ...]:
    instruction = (
        "Return JSON with exactly answer and sentence_ids. Write an original, "
        "grounded answer using only the candidate excerpts. sentence_ids must "
        "contain the candidate IDs supporting the answer; do not put citations "
        "or source markers in answer."
    )
    if repair:
        instruction += " This is the only repair attempt; correct every validation issue."
    passages = "\n\n".join(
        f"candidate_id={item.candidate_id}\n{item.excerpt}" for item in evidence
    )
    return (
        GenerationMessage(role="system", content=instruction),
        GenerationMessage(role="user", content=f"Question: {question}\n\nEvidence:\n{passages}"),
    )


def _validated_candidate(
    body: str,
    *,
    evidence: Sequence[EvidenceSnapshot],
    required_sources: int,
) -> tuple[str, tuple[AnswerCitation, ...], tuple[EvidenceSnapshot, ...]] | None:
    """Parse and validate untrusted synthesis output before it can be visible."""

    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return None
    if set(payload) != {"answer", "sentence_ids"}:
        return None
    answer = payload.get("answer")
    candidate_ids = payload.get("sentence_ids")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(candidate_ids, list):
        return None
    if any(not isinstance(item, str) for item in candidate_ids):
        return None
    if len(candidate_ids) != len(set(candidate_ids)):
        return None
    by_candidate = {item.candidate_id: item for item in evidence}
    try:
        selected = tuple(by_candidate[item] for item in candidate_ids)
    except KeyError:
        return None
    if not _has_required_distinct_sources(selected, required_sources):
        return None
    if any(f"[{item}]" in answer for item in candidate_ids):
        return None
    citations = tuple(
        AnswerCitation(
            candidate_id=item.candidate_id,
            book_id=item.book_id,
            chunk_id=item.chunk_id,
        )
        for item in selected
    )
    return answer.strip(), citations, selected


def _result(
    request: AnswerRequest,
    outcome: str,
    answer: str,
    citations: Sequence[AnswerCitation] = (),
) -> AnswerResult:
    return AnswerResult(
        request_id=request.request_id,
        outcome=outcome,
        answer=answer,
        citations=tuple(citations),
    )
