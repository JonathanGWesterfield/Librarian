"""Immutable answer-runtime values shared by the runtime and its adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType

ANSWER_EVENT_SCHEMA_VERSION = "v1"
MAX_EVIDENCE_EXCERPT_BYTES = 8 * 1024
MAX_EVIDENCE_CANDIDATES = 32
MAX_EVIDENCE_SNAPSHOT_BYTES = 256 * 1024


def _immutable_mapping(values: Mapping[str, str] | None) -> Mapping[str, str]:
    return MappingProxyType(dict(values or {}))


@dataclass(frozen=True)
class AnswerScope:
    """The effective retrieval scope used for an answer request."""

    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class EvidenceSnapshot:
    """One immutable, server-only source candidate for a single answer run."""

    candidate_id: str
    book_id: str
    chunk_id: str
    source_revision: str
    source_sha256: str
    effective_scope: Mapping[str, str] = field(default_factory=dict)
    body_text_eligible: bool = True
    retrieval_provenance: Mapping[str, str] = field(default_factory=dict)
    excerpt: str = ""
    book_title: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.book_id or not self.chunk_id:
            raise ValueError("evidence snapshot requires candidate, book, and chunk IDs")
        if not self.source_revision:
            raise ValueError("evidence snapshot requires a source revision")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("source_sha256 must be a lowercase SHA-256 hex digest")
        if len(self.excerpt.encode("utf-8")) > MAX_EVIDENCE_EXCERPT_BYTES:
            raise ValueError("evidence excerpt exceeds the 8 KiB limit")
        object.__setattr__(self, "effective_scope", _immutable_mapping(self.effective_scope))
        object.__setattr__(
            self,
            "retrieval_provenance",
            _immutable_mapping(self.retrieval_provenance),
        )

    @classmethod
    def from_source_record(
        cls,
        *,
        candidate_id: str,
        source: SourceRecord,
        effective_scope: Mapping[str, str] | None = None,
        body_text_eligible: bool,
        retrieval_provenance: Mapping[str, str] | None = None,
        excerpt: str | None = None,
        book_title: str | None = None,
    ) -> EvidenceSnapshot:
        return cls(
            candidate_id=candidate_id,
            book_id=source.book_id,
            chunk_id=source.chunk_id,
            source_revision=source.source_revision,
            source_sha256=source.content_sha256,
            effective_scope=effective_scope or {},
            body_text_eligible=body_text_eligible,
            retrieval_provenance=retrieval_provenance or {},
            excerpt=source.text if excerpt is None else excerpt,
            book_title=book_title,
        )


@dataclass(frozen=True)
class SourceRecord:
    """The source-of-truth record used to create or reload evidence."""

    book_id: str
    chunk_id: str
    source_revision: str
    text: str
    content_type: str = "body"

    @property
    def content_sha256(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AnswerRequest:
    request_id: str
    question: str
    scope: AnswerScope = field(default_factory=AnswerScope)
    evidence_snapshot: tuple[EvidenceSnapshot, ...] = ()
    minimum_citation_count: int = 1

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("answer request requires a request ID")
        if not self.question.strip():
            raise ValueError("answer request question must not be empty")
        if self.minimum_citation_count < 1 or self.minimum_citation_count > MAX_EVIDENCE_CANDIDATES:
            raise ValueError("answer request minimum citation count must be between 1 and 32")
        snapshots = tuple(self.evidence_snapshot)
        if len(snapshots) > MAX_EVIDENCE_CANDIDATES:
            raise ValueError("answer request exceeds the 32-candidate evidence limit")
        if sum(len(item.excerpt.encode("utf-8")) for item in snapshots) > MAX_EVIDENCE_SNAPSHOT_BYTES:
            raise ValueError("answer request exceeds the 256 KiB evidence limit")
        object.__setattr__(self, "evidence_snapshot", snapshots)


@dataclass(frozen=True)
class AnswerCitation:
    candidate_id: str
    book_id: str
    chunk_id: str


@dataclass(frozen=True)
class AnswerResult:
    """The one authoritative terminal result assembled by the runtime."""

    request_id: str
    outcome: str
    answer: str
    citations: tuple[AnswerCitation, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "citations", tuple(self.citations))


@dataclass(frozen=True)
class AnswerEvent:
    schema_version: str
    request_id: str
    sequence: int
    event: str
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != ANSWER_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported answer event schema version")
        if not self.request_id or self.sequence <= 0 or not self.event:
            raise ValueError("answer event requires request ID, positive sequence, and event")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class GenerationMessage:
    role: str
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    operation: str
    messages: tuple[GenerationMessage, ...]
    response_format: str | None = None
    repair_hint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))


@dataclass(frozen=True)
class GenerationResult:
    body: str
    provider: str
    model: str
    repair_hint: str | None = None
    repairable: bool = True


@dataclass(frozen=True)
class SupportReviewRequest:
    question: str
    answer: str
    citations: tuple[AnswerCitation, ...]
    evidence_snapshot: tuple[EvidenceSnapshot, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "citations", tuple(self.citations))
        object.__setattr__(self, "evidence_snapshot", tuple(self.evidence_snapshot))


@dataclass(frozen=True)
class SupportReviewResult:
    supported: bool
    reason: str = ""
