"""R1 adapters from existing Librarian implementations to answer-runtime ports."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from librarian_answer.models import (
    AnswerCitation,
    AnswerRequest,
    EvidenceSnapshot,
    GenerationMessage,
    GenerationRequest,
    GenerationResult,
    SourceRecord,
    SupportReviewRequest,
    SupportReviewResult,
)
from librarian_answer.ports import RequestContext
from librarian_chat.chat import ChatSource, SynthesisSupportJudge
from librarian_chat.generation import ChatMessage, Generator
from librarian_evaluation.answer import AnswerCandidate, AnswerEvaluationCase, AnswerSource
from librarian_evaluation.llm_judge import evaluate_answers_with_llm_judge
from librarian_storage.storage import IngestionStore


LegacySourceRetriever = Callable[[AnswerRequest], Sequence[ChatSource]]
IngestionStoreFactory = Callable[[], IngestionStore]


@dataclass(frozen=True)
class LegacyEvidenceRetriever:
    """Adapts R1 chat retrieval and SQLite source records to runtime evidence."""

    retrieve_sources: LegacySourceRetriever
    store_factory: IngestionStoreFactory
    retrieval_backend: str

    def retrieve(
        self, request: AnswerRequest, context: RequestContext
    ) -> tuple[EvidenceSnapshot, ...]:
        if context.is_cancelled():
            return ()
        scope = {
            key: value
            for key, value in {
                "book_id": request.scope.book_id,
                "book_title": request.scope.book_title,
                "author": request.scope.author,
            }.items()
            if value
        }
        snapshots: list[EvidenceSnapshot] = []
        for source in self.retrieve_sources(request):
            record = self.reload_source(book_id=source.book_id, chunk_id=source.chunk_id)
            if record is None:
                continue
            retrieved = SourceRecord(
                book_id=source.book_id,
                chunk_id=source.chunk_id,
                source_revision=record.source_revision,
                text=source.text,
                content_type=source.content_type,
            )
            snapshots.append(
                EvidenceSnapshot.from_source_record(
                    candidate_id=source.source_id,
                    source=retrieved,
                    effective_scope=scope,
                    body_text_eligible=source.content_type == "body",
                    retrieval_provenance={
                        "backend": self.retrieval_backend,
                        "legacy_source_id": source.source_id,
                        "relative_path": source.relative_path,
                    },
                    excerpt=_bounded_excerpt(source.text),
                    book_title=source.title,
                )
            )
        return tuple(snapshots)

    def reload_source(self, *, book_id: str, chunk_id: str) -> SourceRecord | None:
        store = self.store_factory()
        try:
            store.initialize()
            chunk = store.get_source_chunk(book_id=book_id, chunk_id=chunk_id)
            if chunk is None:
                return None
            return SourceRecord(
                book_id=chunk.book_id,
                chunk_id=chunk.id,
                source_revision=chunk.source_revision,
                text=chunk.text,
                content_type=chunk.content_type,
            )
        finally:
            store.close()


@dataclass(frozen=True)
class LegacyGenerationBroker:
    """Adapts the configured R1 generator, including its HTTP broker target."""

    generator: Generator

    def generate(
        self, request: GenerationRequest, context: RequestContext
    ) -> GenerationResult:
        if context.is_cancelled():
            raise RuntimeError("answer request was cancelled before generation")
        body = self.generator.generate(
            [
                ChatMessage(role=message.role, content=message.content)
                for message in request.messages
            ],
            response_format=request.response_format,
        )
        return GenerationResult(
            body=body,
            provider=self.generator.provider,
            model=self.generator.model,
        )


@dataclass(frozen=True)
class LegacySupportReviewer:
    """Reuses R1's enforcing semantic-review implementation behind a port."""

    generator: Generator
    _judge: SynthesisSupportJudge = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_judge", SynthesisSupportJudge(self.generator))

    def review(
        self, request: SupportReviewRequest, context: RequestContext
    ) -> SupportReviewResult:
        if context.is_cancelled():
            raise RuntimeError("answer request was cancelled before support review")
        sources_by_candidate = {
            snapshot.candidate_id: snapshot for snapshot in request.evidence_snapshot
        }
        cited_sources: list[AnswerSource] = []
        legacy_citation_ids: list[str] = []
        for citation in request.citations:
            snapshot = sources_by_candidate.get(citation.candidate_id)
            if snapshot is None:
                continue
            source_id = snapshot.retrieval_provenance.get(
                "legacy_source_id", citation.candidate_id
            )
            cited_sources.append(
                AnswerSource(
                    source_id=source_id,
                    text=snapshot.excerpt,
                    relative_path=snapshot.retrieval_provenance.get("relative_path"),
                )
            )
            legacy_citation_ids.append(source_id)
        answer = _answer_with_legacy_citations(request.answer, legacy_citation_ids)
        scope = (
            dict(request.evidence_snapshot[0].effective_scope)
            if request.evidence_snapshot
            else {}
        )
        report = evaluate_answers_with_llm_judge(
            [AnswerEvaluationCase(id="answer-runtime", question=request.question, scope=scope)],
            {"answer-runtime": AnswerCandidate(answer=answer, sources=cited_sources)},
            judge=self._judge,
        )
        verdict = report.cases[0]
        supported = (
            verdict.evidence_verdict == "supported"
            and verdict.citation_relevance == "all_relevant"
            and not verdict.missing_coverage
            and not verdict.unsupported_claims
        )
        return SupportReviewResult(supported=supported, reason=verdict.reason)


def _answer_with_legacy_citations(answer: str, citation_ids: list[str]) -> str:
    """Give the R1 judge its existing citation form without changing prose."""

    missing = [source_id for source_id in citation_ids if f"[{source_id}]" not in answer]
    if not missing:
        return answer
    suffix = " ".join(f"[{source_id}]" for source_id in missing)
    return f"{answer.rstrip()} {suffix}".strip()


def _bounded_excerpt(text: str) -> str:
    """Retain valid UTF-8 while enforcing the runtime's 8 KiB excerpt bound."""

    return text.encode("utf-8")[: 8 * 1024].decode("utf-8", errors="ignore")
