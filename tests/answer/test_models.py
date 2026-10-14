import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import (
    ANSWER_EVENT_SCHEMA_VERSION,
    AnswerEvent,
    AnswerRequest,
    AnswerScope,
    EvidenceSnapshot,
    SourceFreshness,
    SourceRecord,
    reload_citation_sources,
    reload_snapshot_source,
)


class AnswerRuntimeModelTests(unittest.TestCase):
    def test_request_and_snapshot_copy_mutable_inputs(self) -> None:
        scope = {"book_id": "book-1"}
        provenance = {"backend": "sqlite"}
        source = SourceRecord(
            book_id="book-1",
            chunk_id="chunk-1",
            source_revision="revision-1",
            text="A grounded passage.",
        )
        snapshot = EvidenceSnapshot.from_source_record(
            candidate_id="candidate-1",
            source=source,
            effective_scope=scope,
            body_text_eligible=True,
            retrieval_provenance=provenance,
        )
        request = AnswerRequest(
            request_id="request-1",
            question="What happened?",
            scope=AnswerScope(book_id="book-1"),
            evidence_snapshot=[snapshot],
        )
        scope["book_id"] = "changed"
        provenance["backend"] = "changed"

        self.assertEqual(snapshot.effective_scope["book_id"], "book-1")
        self.assertEqual(snapshot.retrieval_provenance["backend"], "sqlite")
        self.assertIsInstance(request.evidence_snapshot, tuple)
        with self.assertRaises(TypeError):
            snapshot.effective_scope["book_id"] = "changed"  # type: ignore[index]

    def test_evidence_limits_and_sha_validation_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            EvidenceSnapshot(
                candidate_id="candidate-1",
                book_id="book-1",
                chunk_id="chunk-1",
                source_revision="revision-1",
                source_sha256="invalid",
            )
        source = SourceRecord(
            book_id="book-1",
            chunk_id="chunk-1",
            source_revision="revision-1",
            text="text",
        )
        snapshot = EvidenceSnapshot.from_source_record(
            candidate_id="candidate-1", source=source, body_text_eligible=True
        )
        with self.assertRaisesRegex(ValueError, "32-candidate"):
            AnswerRequest(
                request_id="request-1",
                question="What happened?",
                evidence_snapshot=[snapshot] * 33,
            )

    def test_event_copies_payload_and_requires_a_positive_sequence(self) -> None:
        payload = {"candidate_count": 1}
        event = AnswerEvent(
            schema_version=ANSWER_EVENT_SCHEMA_VERSION,
            request_id="request-1",
            sequence=1,
            event="started",
            payload=payload,
        )
        payload["candidate_count"] = 2
        self.assertEqual(event.payload["candidate_count"], 1)
        with self.assertRaisesRegex(ValueError, "positive sequence"):
            AnswerEvent(
                schema_version=ANSWER_EVENT_SCHEMA_VERSION,
                request_id="request-1",
                sequence=0,
                event="started",
            )

    def test_source_reload_requires_exact_revision_and_content_sha(self) -> None:
        original = SourceRecord(
            book_id="book-1",
            chunk_id="chunk-1",
            source_revision="revision-1",
            text="Original body text.",
        )
        snapshot = EvidenceSnapshot.from_source_record(
            candidate_id="candidate-1", source=original, body_text_eligible=True
        )

        current = reload_snapshot_source(
            snapshot, lambda _book_id, _chunk_id: original
        )
        changed_content = reload_snapshot_source(
            snapshot,
            lambda _book_id, _chunk_id: SourceRecord(
                book_id="book-1",
                chunk_id="chunk-1",
                source_revision="revision-1",
                text="Replacement body text.",
            ),
        )
        changed_revision = reload_citation_sources(
            (snapshot,),
            lambda _book_id, _chunk_id: SourceRecord(
                book_id="book-1",
                chunk_id="chunk-1",
                source_revision="revision-2",
                text="Original body text.",
            ),
        )
        changed_chunk = reload_snapshot_source(
            snapshot,
            lambda _book_id, _chunk_id: SourceRecord(
                book_id="book-1",
                chunk_id="replacement-chunk",
                source_revision="revision-1",
                text="Original body text.",
            ),
        )

        self.assertTrue(current.is_current)
        self.assertEqual(changed_content.status, SourceFreshness.SOURCE_CHANGED)
        self.assertEqual(changed_revision, SourceFreshness.SOURCE_CHANGED)
        self.assertEqual(changed_chunk.status, SourceFreshness.SOURCE_CHANGED)
