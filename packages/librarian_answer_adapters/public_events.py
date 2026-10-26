"""Safe public v1 event projection for the in-process answer runtime.

The runtime owns grounding, validation, and the lifecycle.  This adapter only
whitelists its already-validated events for the browser's JSON/SSE contract.
It intentionally has no retrieval, generation, or broker dependency.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from librarian_answer import ANSWER_EVENT_SCHEMA_VERSION, AnswerEvent

_TERMINAL_EVENTS = frozenset({"completed", "failed", "cancelled"})
_PROGRESS_EVENTS = frozenset(
    {"started", "evidence_candidates", "generation_started", "validation_started"}
)
_RESULT_EVENTS = frozenset({"answer_validated", "completed"})
_ALLOWED_SUCCESSORS = {
    "started": frozenset({"evidence_candidates", "completed", "failed", "cancelled"}),
    "evidence_candidates": frozenset(
        {"generation_started", "completed", "failed", "cancelled"}
    ),
    "generation_started": frozenset(
        {"validation_started", "completed", "failed", "cancelled"}
    ),
    "validation_started": frozenset(
        {
            "generation_started",
            "answer_validated",
            "completed",
            "failed",
            "cancelled",
        }
    ),
    "answer_validated": frozenset({"completed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
_MAX_SSE_FRAME_BYTES = 128 * 1024


class SseFrameTooLargeError(ValueError):
    """Raised before a public event can exceed the v1 SSE frame limit."""


@dataclass
class PublicAnswerEventSerializer:
    """Validate one runtime lifecycle and project it onto the public schema.

    ``result`` is the API-owned, fully populated response mapping associated
    with a runtime terminal result.  It is deliberately ignored for progress
    events, which prevents a future runtime payload from leaking draft prose or
    source excerpts before validation.
    """

    request_id: str
    _last_sequence: int = field(default=0, init=False)
    _last_event: str | None = field(default=None, init=False)
    _terminal_seen: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _canonical_uuid(self.request_id)

    def serialize(
        self, event: AnswerEvent, *, result: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        """Return one schema-shaped public event or reject an invalid lifecycle."""

        self._validate_envelope(event)
        payload: dict[str, object] = {
            "schema_version": ANSWER_EVENT_SCHEMA_VERSION,
            "request_id": self.request_id,
            "sequence": event.sequence,
            "event": event.event,
        }
        if event.event == "evidence_candidates":
            payload.update(_candidate_progress(event.payload))
        elif event.event in {"generation_started", "validation_started"}:
            payload["attempt"] = _attempt(event.payload)
        elif event.event in _RESULT_EVENTS:
            if result is None:
                raise ValueError(f"{event.event} requires an API result")
            public_result = _public_result(result)
            if event.event == "answer_validated" and public_result["outcome"] != "answered":
                raise ValueError("answer_validated requires an answered result")
            payload["result"] = public_result
        elif event.event == "failed":
            # Runtime port errors can carry implementation-specific details.
            # The browser receives only a bounded, stable safe error instead.
            payload["error"] = {
                "code": "internal_error",
                "message": "Answer delivery failed.",
                "retryable": False,
            }
        elif event.event == "cancelled":
            pass
        elif event.event != "started":
            raise ValueError(f"unsupported answer event: {event.event}")

        # A public projection is only committed after its complete SSE frame
        # fits.  This leaves the prior state available for a safe failure event
        # when a terminal result is too large to deliver.
        encode_sse_event(payload)
        self._last_sequence = event.sequence
        self._last_event = event.event
        self._terminal_seen = event.event in _TERMINAL_EVENTS
        return payload

    def serialize_failure(self, *, sequence: int) -> dict[str, object]:
        """Project a bounded delivery failure at the rejected event's sequence.

        The caller uses this after a result payload cannot fit into a complete
        SSE frame.  It deliberately uses the normal transition validation, so
        a late failure cannot follow ``answer_validated`` or a terminal event.
        """

        return self.serialize(
            AnswerEvent(
                schema_version=ANSWER_EVENT_SCHEMA_VERSION,
                request_id=self.request_id,
                sequence=sequence,
                event="failed",
            )
        )

    def _validate_envelope(self, event: AnswerEvent) -> None:
        if event.schema_version != ANSWER_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported answer event schema version")
        if event.request_id != self.request_id:
            raise ValueError("answer event request ID changed during delivery")
        if self._terminal_seen:
            raise ValueError("answer event arrived after a terminal event")
        if event.sequence != self._last_sequence + 1:
            raise ValueError("answer event sequence must be strictly contiguous")
        if event.event not in _PROGRESS_EVENTS | _RESULT_EVENTS | _TERMINAL_EVENTS:
            raise ValueError(f"unsupported answer event: {event.event}")
        if self._last_event is None:
            if event.event != "started":
                raise ValueError("answer event lifecycle must start with started")
            return
        if event.event not in _ALLOWED_SUCCESSORS[self._last_event]:
            raise ValueError(
                f"answer event {event.event} cannot follow {self._last_event}"
            )


def encode_sse_event(payload: Mapping[str, object]) -> bytes:
    """Encode one validated public event as exactly one SSE frame."""

    request_id = payload.get("request_id")
    sequence = payload.get("sequence")
    event_name = payload.get("event")
    if not isinstance(request_id, str) or not isinstance(sequence, int) or not isinstance(event_name, str):
        raise TypeError("public answer event is missing its SSE envelope")
    data = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=False)
    frame = f"id: {request_id}:{sequence}\nevent: {event_name}\ndata: {data}\n\n".encode()
    if len(frame) > _MAX_SSE_FRAME_BYTES:
        raise SseFrameTooLargeError("public answer event exceeds the 128 KiB SSE limit")
    return frame


def _canonical_uuid(value: str) -> None:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as error:
        raise ValueError("answer event request ID must be a canonical UUID") from error
    if str(parsed) != value:
        raise ValueError("answer event request ID must be a canonical UUID")


def _candidate_progress(values: Mapping[str, object]) -> dict[str, object]:
    count = values.get("candidate_count")
    candidates = values.get("candidates")
    if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 128:
        raise ValueError("candidate progress requires a bounded count")
    if not isinstance(candidates, (list, tuple)) or len(candidates) > 32:
        raise ValueError("candidate progress requires at most 32 candidates")
    public_candidates: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise TypeError("candidate progress must be objects")
        if set(candidate) != {"candidate_id", "book_id", "book_title"}:
            raise ValueError("candidate progress contains a non-public field")
        candidate_id = candidate["candidate_id"]
        book_id = candidate["book_id"]
        book_title = candidate["book_title"]
        if not isinstance(candidate_id, str) or not candidate_id or len(candidate_id) > 128:
            raise ValueError("candidate progress has an invalid candidate ID")
        if not isinstance(book_id, str) or not book_id or len(book_id) > 128:
            raise ValueError("candidate progress has an invalid book ID")
        if book_title is not None and (not isinstance(book_title, str) or len(book_title) > 512):
            raise ValueError("candidate progress has an invalid book title")
        public_candidates.append(
            {
                "candidate_id": candidate_id,
                "book_id": book_id,
                "book_title": book_title,
            }
        )
    return {"candidate_count": count, "candidates": public_candidates}


def _attempt(values: Mapping[str, object]) -> int:
    attempt = values.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or not 1 <= attempt <= 2:
        raise ValueError("answer progress attempt must be between 1 and 2")
    return attempt


def _public_result(result: Mapping[str, object]) -> dict[str, object]:
    """Copy the exact public result fields and reject an incomplete projection."""

    required = {
        "outcome",
        "minimum_citation_count",
        "citation_count",
        "question",
        "answer",
        "embedding_provider",
        "embedding_model",
        "generation_provider",
        "generation_model",
        "answer_capability",
        "retrieval_limit",
        "candidate_count",
        "filters",
        "retrieval_backend",
        "sources",
        "timings",
    }
    if set(result) != required:
        raise ValueError("public answer result does not match the v1 schema")
    if result.get("outcome") not in {
        "answered",
        "insufficient_evidence",
        "generation_unavailable",
        "source_changed",
    }:
        raise ValueError("public answer result has an invalid outcome")
    if result.get("answer_capability") not in {"quality", "lightweight"}:
        raise ValueError("public answer result has an invalid answer capability")
    if result.get("retrieval_backend") not in {"opensearch", "sqlite"}:
        raise ValueError("public answer result has an invalid retrieval backend")
    timings = result.get("timings")
    timing_fields = {
        "query_embedding_seconds",
        "retrieval_seconds",
        "prompt_construction_seconds",
        "generation_seconds",
        "validation_seconds",
        "repair_seconds",
        "total_seconds",
    }
    if not isinstance(timings, Mapping) or set(timings) != timing_fields:
        raise ValueError("public answer result timings do not match the v1 schema")
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < 0
        for value in timings.values()
    ):
        raise ValueError("public answer result timings must be non-negative numbers")
    return dict(result)
