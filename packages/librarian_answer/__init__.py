"""In-process domain contracts for Librarian answer delivery.

The runtime is deliberately independent of HTTP, FastAPI, storage, search, and
provider implementations.  M02 adapters translate those implementation types
at the composition boundary.
"""

from librarian_answer.models import (
    ANSWER_EVENT_SCHEMA_VERSION,
    MAX_EVIDENCE_CANDIDATES,
    MAX_EVIDENCE_EXCERPT_BYTES,
    MAX_EVIDENCE_SNAPSHOT_BYTES,
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
from librarian_answer.snapshots import (
    SourceFreshness,
    SourceReloadResult,
    reload_citation_sources,
    reload_snapshot_source,
)

__all__ = [
    "ANSWER_EVENT_SCHEMA_VERSION",
    "MAX_EVIDENCE_CANDIDATES",
    "MAX_EVIDENCE_EXCERPT_BYTES",
    "MAX_EVIDENCE_SNAPSHOT_BYTES",
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
    "SourceFreshness",
    "SourceRecord",
    "SourceReloadResult",
    "SupportReviewRequest",
    "SupportReviewResult",
    "SupportReviewer",
    "reload_citation_sources",
    "reload_snapshot_source",
]
