from __future__ import annotations

import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import (  # noqa: E402
    AnswerCitation,
    AnswerRequest,
    EvidenceSnapshot,
    GenerationMessage,
    GenerationRequest,
    SourceRecord,
    SupportReviewRequest,
    reload_snapshot_source,
)
from librarian_answer.adapters import (  # noqa: E402
    LegacyEvidenceRetriever,
    LegacyGenerationBroker,
    LegacySupportReviewer,
)
from librarian_chat.chat import ChatSource  # noqa: E402


@dataclass
class _Context:
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def remaining_seconds(self) -> float | None:
        return 30.0


@dataclass
class _Generator:
    response: str
    provider: str = "docker_codex_broker"
    model: str = "test-model"
    messages: list[object] | None = None
    response_format: str | None = None

    def generate(self, messages: list[object], *, response_format: str | None = None) -> str:
        self.messages = messages
        self.response_format = response_format
        return self.response


class _Chunk:
    def __init__(self, *, text: str, revision: str = "revision-1") -> None:
        self.id = "chunk-1"
        self.book_id = "book-1"
        self.text = text
        self.source_revision = revision
        self.content_type = "body"


class _Store:
    def __init__(self, chunk: _Chunk | None) -> None:
        self.chunk = chunk
        self.initialized = False
        self.closed = False

    def initialize(self) -> None:
        self.initialized = True

    def get_source_chunk(self, *, book_id: str, chunk_id: str) -> _Chunk | None:
        if book_id == "book-1" and chunk_id == "chunk-1":
            return self.chunk
        return None

    def close(self) -> None:
        self.closed = True


class AnswerRuntimeAdapterTests(unittest.TestCase):
    def test_retrieval_adapter_records_r1_provenance_and_reloads_source(self) -> None:
        store = _Store(_Chunk(text="Current source text."))
        source = ChatSource(
            source_id="S1",
            score=0.9,
            chunk_id="chunk-1",
            book_id="book-1",
            relative_path="book.epub",
            title="A Book",
            authors=["An Author"],
            chunk_index=0,
            text="Indexed source text.",
        )
        adapter = LegacyEvidenceRetriever(
            retrieve_sources=lambda _request: [source],
            store_factory=lambda: store,  # type: ignore[arg-type]
            retrieval_backend="opensearch",
        )

        snapshots = adapter.retrieve(
            AnswerRequest(request_id="request-1", question="What happened?"), _Context()
        )

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].retrieval_provenance["backend"], "opensearch")
        self.assertEqual(snapshots[0].retrieval_provenance["legacy_source_id"], "S1")
        self.assertTrue(store.initialized)
        self.assertTrue(store.closed)
        self.assertFalse(
            reload_snapshot_source(snapshots[0], lambda _book, _chunk: SourceRecord(
                book_id="book-1", chunk_id="chunk-1", source_revision="revision-1",
                text="Current source text.",
            )).is_current
        )

    def test_generation_adapter_preserves_legacy_generator_contract(self) -> None:
        generator = _Generator(response="generated")
        result = LegacyGenerationBroker(generator).generate(
            GenerationRequest(
                operation="GROUNDED_SYNTHESIS",
                messages=[GenerationMessage(role="user", content="Question")],
                response_format="grounded_chat_synthesis",
            ),
            _Context(),
        )

        self.assertEqual(result.body, "generated")
        self.assertEqual((result.provider, result.model), ("docker_codex_broker", "test-model"))
        assert generator.messages is not None
        self.assertEqual(generator.messages[0].content, "Question")
        self.assertEqual(generator.response_format, "grounded_chat_synthesis")

    def test_support_review_adapter_uses_r1_enforcing_judge(self) -> None:
        generator = _Generator(response=json.dumps({
            "evidence_verdict": "supported",
            "citation_relevance": "all_relevant",
            "missing_coverage": [],
            "unsupported_claims": [],
            "reason": "The citation supports the answer.",
        }))
        source = SourceRecord(
            book_id="book-1", chunk_id="chunk-1", source_revision="revision-1",
            text="Mara opens the gate.",
        )
        snapshot = EvidenceSnapshot.from_source_record(
            candidate_id="candidate-1",
            source=source,
            body_text_eligible=True,
            retrieval_provenance={"legacy_source_id": "S1", "relative_path": "book.epub"},
        )
        result = LegacySupportReviewer(generator).review(
            SupportReviewRequest(
                question="Who opens the gate?",
                answer="Mara opens the gate.",
                citations=[AnswerCitation("candidate-1", "book-1", "chunk-1")],
                evidence_snapshot=[snapshot],
            ),
            _Context(),
        )

        self.assertTrue(result.supported)
        self.assertEqual(result.reason, "The citation supports the answer.")
        self.assertEqual(generator.response_format, "json")
