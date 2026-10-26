"""Deterministic coverage for the public v1 runtime-to-SSE projection."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import AnswerEvent
from librarian_answer_adapters.public_events import (
    PublicAnswerEventSerializer,
    SseFrameTooLargeError,
    encode_sse_event,
)

_REQUEST_ID = "0d4f7c96-49f6-4ea0-8804-3b4fd3d55692"


def _result() -> dict[str, object]:
    return {
        "outcome": "answered",
        "minimum_citation_count": 1,
        "citation_count": 1,
        "question": "Who opens the gate?",
        "answer": "Mara opens the gate. [S1]",
        "embedding_provider": "ollama",
        "embedding_model": "all-minilm",
        "generation_provider": "grpc",
        "generation_model": "fixture-model",
        "answer_capability": "quality",
        "retrieval_limit": 1,
        "candidate_count": 1,
        "filters": {"book_id": "book-1"},
        "retrieval_backend": "sqlite",
        "sources": [],
        "timings": {
            "query_embedding_seconds": 0.01,
            "retrieval_seconds": 0.02,
            "prompt_construction_seconds": 0.0,
            "generation_seconds": 0.03,
            "validation_seconds": 0.0,
            "repair_seconds": 0.0,
            "total_seconds": 0.06,
        },
    }


class PublicAnswerEventSerializerTests(unittest.TestCase):
    def test_runtime_events_become_one_schema_shaped_sse_frame_each(self) -> None:
        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        runtime_events = [
            AnswerEvent("v1", _REQUEST_ID, 1, "started"),
            AnswerEvent(
                "v1",
                _REQUEST_ID,
                2,
                "evidence_candidates",
                {
                    "candidate_count": 1,
                    "candidates": (
                        {
                            "candidate_id": "candidate-1",
                            "book_id": "book-1",
                            "book_title": "Fixture Book",
                        },
                    ),
                },
            ),
            AnswerEvent("v1", _REQUEST_ID, 3, "generation_started", {"attempt": 1}),
            AnswerEvent("v1", _REQUEST_ID, 4, "validation_started", {"attempt": 1}),
            AnswerEvent("v1", _REQUEST_ID, 5, "answer_validated", {"result": object()}),
            AnswerEvent("v1", _REQUEST_ID, 6, "completed", {"result": object()}),
        ]

        public = [
            serializer.serialize(event, result=_result() if event.event in {"answer_validated", "completed"} else None)
            for event in runtime_events
        ]

        self.assertEqual([event["event"] for event in public], [event.event for event in runtime_events])
        self.assertEqual([event["sequence"] for event in public], [1, 2, 3, 4, 5, 6])
        self.assertEqual(public[4]["result"], public[5]["result"])
        frame = encode_sse_event(public[1]).decode("utf-8")
        self.assertTrue(frame.startswith(f"id: {_REQUEST_ID}:2\nevent: evidence_candidates\n"))
        decoded = json.loads(frame.split("data: ", 1)[1])
        self.assertEqual(decoded, public[1])

    def test_progress_whitelist_rejects_excerpts_and_draft_answer_prose(self) -> None:
        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 1, "started"))
        with self.assertRaisesRegex(ValueError, "non-public field"):
            serializer.serialize(
                AnswerEvent(
                    "v1",
                    _REQUEST_ID,
                    2,
                    "evidence_candidates",
                    {
                        "candidate_count": 1,
                        "candidates": (
                            {
                                "candidate_id": "candidate-1",
                                "book_id": "book-1",
                                "book_title": "Fixture Book",
                                "excerpt": "Private source text",
                            },
                        ),
                    },
                )
            )

    def test_terminal_event_blocks_a_late_completion_and_failure_is_safe(self) -> None:
        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 1, "started"))
        failed = serializer.serialize(
            AnswerEvent("v1", _REQUEST_ID, 2, "failed", {"error": "provider stderr"})
        )
        self.assertEqual(
            failed["error"],
            {
                "code": "internal_error",
                "message": "Answer delivery failed.",
                "retryable": False,
            },
        )
        with self.assertRaisesRegex(ValueError, "after a terminal"):
            serializer.serialize(
                AnswerEvent("v1", _REQUEST_ID, 3, "completed", {"result": object()}),
                result=_result(),
            )

    def test_cancelled_terminal_blocks_a_late_completion(self) -> None:
        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 1, "started"))
        cancelled = serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 2, "cancelled"))
        self.assertEqual(set(cancelled), {"schema_version", "request_id", "sequence", "event"})
        with self.assertRaisesRegex(ValueError, "after a terminal"):
            serializer.serialize(
                AnswerEvent("v1", _REQUEST_ID, 3, "completed", {"result": object()}),
                result=_result(),
            )

    def test_lifecycle_rejects_skipped_and_post_validation_states(self) -> None:
        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 1, "started"))
        with self.assertRaisesRegex(ValueError, "cannot follow started"):
            serializer.serialize(
                AnswerEvent("v1", _REQUEST_ID, 2, "answer_validated", {"result": object()}),
                result=_result(),
            )

        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 1, "started"))
        serializer.serialize(
            AnswerEvent(
                "v1",
                _REQUEST_ID,
                2,
                "evidence_candidates",
                {
                    "candidate_count": 0,
                    "candidates": (),
                },
            )
        )
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 3, "generation_started", {"attempt": 1}))
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 4, "validation_started", {"attempt": 1}))
        serializer.serialize(
            AnswerEvent("v1", _REQUEST_ID, 5, "answer_validated", {"result": object()}),
            result=_result(),
        )
        for invalid_successor in (
            "started",
            "evidence_candidates",
            "generation_started",
            "validation_started",
            "answer_validated",
            "failed",
            "cancelled",
        ):
            with self.subTest(invalid_successor=invalid_successor):
                with self.assertRaisesRegex(ValueError, "cannot follow answer_validated"):
                    serializer.serialize(
                        AnswerEvent("v1", _REQUEST_ID, 6, invalid_successor)
                    )

    def test_sse_frame_limit_uses_utf8_bytes_and_safe_failure_remains_valid(self) -> None:
        serializer = PublicAnswerEventSerializer(_REQUEST_ID)
        serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 1, "started"))
        result = _result()
        # 44,000 characters are below 128 KiB by character count but exceed it
        # once the UTF-8 answer and the complete SSE envelope are encoded.
        result["answer"] = "界" * 44_000
        with self.assertRaises(SseFrameTooLargeError):
            serializer.serialize(
                AnswerEvent("v1", _REQUEST_ID, 2, "completed", {"result": object()}),
                result=result,
            )

        failed = serializer.serialize_failure(sequence=2)
        self.assertEqual(failed["event"], "failed")
        self.assertLessEqual(len(encode_sse_event(failed)), 128 * 1024)
        with self.assertRaisesRegex(ValueError, "after a terminal"):
            serializer.serialize(AnswerEvent("v1", _REQUEST_ID, 3, "completed"), result=_result())

    def test_sse_frame_limit_accepts_the_exact_byte_boundary(self) -> None:
        payload: dict[str, object] = {
            "schema_version": "v1",
            "request_id": _REQUEST_ID,
            "sequence": 1,
            "event": "started",
            "padding": "",
        }
        padding_bytes = 128 * 1024 - len(encode_sse_event(payload))
        payload["padding"] = "a" * padding_bytes
        self.assertEqual(len(encode_sse_event(payload)), 128 * 1024)

        payload["padding"] += "a"
        with self.assertRaises(SseFrameTooLargeError):
            encode_sse_event(payload)


if __name__ == "__main__":
    unittest.main()
