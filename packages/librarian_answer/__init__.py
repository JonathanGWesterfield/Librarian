"""In-process domain contracts for Librarian answer delivery.

The runtime is deliberately independent of HTTP, FastAPI, storage, search, and
provider implementations.  M02 adapters translate those implementation types
at the composition boundary.
"""

from librarian_answer.models import (
    ANSWER_EVENT_SCHEMA_VERSION,
    AnswerCitation,
    AnswerEvent,
    AnswerRequest,
    AnswerResult,
    AnswerScope,
    EvidenceSnapshot,
    GenerationMessage,
    GenerationRequest,
    GenerationResult,
    SourceRecord,
    SupportReviewRequest,
    SupportReviewResult,
)
from librarian_answer.ports import (
    EvidenceRetriever,
    GenerationBroker,
    RequestContext,
    SupportReviewer,
)

__all__ = [
    "ANSWER_EVENT_SCHEMA_VERSION",
    "AnswerCitation",
    "AnswerEvent",
    "AnswerRequest",
    "AnswerResult",
    "AnswerScope",
    "EvidenceRetriever",
    "EvidenceSnapshot",
    "GenerationBroker",
    "GenerationMessage",
    "GenerationRequest",
    "GenerationResult",
    "RequestContext",
    "SourceRecord",
    "SupportReviewer",
    "SupportReviewRequest",
    "SupportReviewResult",
]
