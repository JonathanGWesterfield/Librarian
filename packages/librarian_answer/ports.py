"""Narrow ports used by the in-process answer runtime."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal, Protocol

from librarian_answer.models import (
    AnswerRequest,
    EvidenceSnapshot,
    GenerationRequest,
    GenerationResult,
    SourceRecord,
    SupportReviewRequest,
    SupportReviewResult,
)

CancellationCause = Literal["explicit", "disconnect", "deadline"]


class RequestContext(Protocol):
    """Request lifecycle state supplied by an API or other composition root."""

    def is_cancelled(self) -> bool:
        """Return whether the caller has cancelled the answer request."""

    def cancellation_cause(self) -> CancellationCause | None:
        """Return the terminal cause, keeping cancellation distinct from deadline."""

    def remaining_seconds(self) -> float | None:
        """Return the remaining end-to-end budget, when one is enforced."""


def resolve_cancellation_cause(context: RequestContext) -> CancellationCause | None:
    """Read the explicit cause while retaining legacy context compatibility."""

    cause_method = getattr(context, "cancellation_cause", None)
    cause = cause_method() if callable(cause_method) else None
    if cause in {"explicit", "disconnect", "deadline"}:
        return cause
    return "explicit" if context.is_cancelled() else None


class EvidenceRetriever(Protocol):
    """Retrieves candidates and reloads source-of-truth evidence records."""

    def retrieve(
        self, request: AnswerRequest, context: RequestContext
    ) -> tuple[EvidenceSnapshot, ...]:
        """Return immutable evidence candidates for one request."""

    def reload_source(self, *, book_id: str, chunk_id: str) -> SourceRecord | None:
        """Reload one exact source record for final citation validation."""


class GenerationBroker(Protocol):
    """Executes a single generation operation without exposing provider types."""

    def generate(
        self, request: GenerationRequest, context: RequestContext
    ) -> GenerationResult | Awaitable[GenerationResult]:
        """Return or await the provider's bounded response and identity."""


class SupportReviewer(Protocol):
    """Reviews a proposed grounded answer against immutable evidence."""

    def review(
        self, request: SupportReviewRequest, context: RequestContext
    ) -> SupportReviewResult | Awaitable[SupportReviewResult]:
        """Return whether the proposed answer is evidence-supported."""
