"""Lifecycle tests for the inactive R2 API-chat composition seam."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer import AnswerRequest, EvidenceSnapshot, SourceRecord
from librarian_api.r2_chat import R2ApiChatCaller, _R2EvidenceRetriever, _RequestContext
from librarian_chat.chat import ChatOptions, ChatResponse, ChatTimings


class R2ApiChatCallerTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_reuses_ready_client_for_all_chat_operations_and_closes_it(self) -> None:
        client = _Client()
        with patch("librarian_api.r2_chat.open_r2_client", AsyncMock(return_value=client)) as open_client:
            caller = await R2ApiChatCaller.open(model_id="gpt-5.6-sol")

        open_client.assert_awaited_once_with(expected_principal="api")
        self.assertIs(caller.operations.client, client)
        self.assertEqual(caller.operations.model_id, "gpt-5.6-sol")
        await caller.close()
        self.assertTrue(client.closed)

    async def test_invalid_model_is_rejected_before_opening_a_channel(self) -> None:
        with (
            patch("librarian_api.r2_chat.open_r2_client", AsyncMock()) as open_client,
            self.assertRaisesRegex(ValueError, "require a model ID"),
        ):
            await R2ApiChatCaller.open(model_id=" ")

        open_client.assert_not_awaited()

    async def test_r2_evidence_retriever_runs_source_selection_before_synthesis(self) -> None:
        snapshot = EvidenceSnapshot.from_source_record(
            candidate_id="S1",
            source=SourceRecord(
                book_id="book-1",
                chunk_id="chunk-1",
                source_revision="r1",
                text="Mara opens the gate.",
            ),
            body_text_eligible=True,
        )
        legacy = _LegacyEvidence((snapshot,))
        operations = _Operations((snapshot,))
        evidence = await _R2EvidenceRetriever(legacy, operations).retrieve(
            AnswerRequest(
                request_id="10000000-0000-4000-8000-000000000001",
                question="Who opens the gate?",
            ),
            _Context(),
        )

        self.assertEqual(evidence, (snapshot,))
        self.assertEqual(operations.minimum_citation_count, 1)
        self.assertEqual(operations.question, "Who opens the gate?")
        self.assertLessEqual(operations.remaining_seconds, 10.0)
        self.assertGreater(operations.remaining_seconds, 9.0)

    async def test_request_context_marks_browser_disconnect_as_cancelled(self) -> None:
        observed = asyncio.Event()

        async def disconnected() -> bool:
            observed.set()
            return True

        context = _RequestContext(is_disconnected=disconnected)
        context.start()
        try:
            await observed.wait()
            await asyncio.sleep(0)
            self.assertTrue(context.is_cancelled())
            self.assertEqual(context.remaining_seconds(), 0.0)
        finally:
            await context.close()

    async def test_r2_rejects_answer_capability_override(self) -> None:
        caller = R2ApiChatCaller(client=_Client(), operations=MagicMock())

        with self.assertRaisesRegex(ValueError, "per-request generation overrides"):
            caller.validate_options(
                ChatOptions(
                    question="Who opens the gate?",
                    answer_capability="quality",
                    answer_capability_is_override=True,
                )
            )

    async def test_disconnect_cancels_while_blocking_retrieval_runs_off_loop(self) -> None:
        started = asyncio.Event()
        disconnect = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def blocking_retrieval(_options):
            loop.call_soon_threadsafe(started.set)
            release.wait(timeout=1)
            raise AssertionError("cancelled retrieval result must be discarded")

        async def is_disconnected() -> bool:
            return disconnect.is_set()

        caller = R2ApiChatCaller(client=_Client(), operations=MagicMock())
        context = _RequestContext(is_disconnected=is_disconnected)
        context.start()
        try:
            with patch("librarian_api.r2_chat.retrieve_chat_evidence", blocking_retrieval):
                answer = asyncio.create_task(
                    caller.answer(ChatOptions(question="Who opens the gate?"), context=context)
                )
                await started.wait()
                disconnect.set()
                with self.assertRaises(asyncio.CancelledError):
                    await answer
        finally:
            release.set()
            await context.close()

    async def test_buffered_r2_stream_keeps_r0_frames_and_required_timings(self) -> None:
        response = _response()
        caller = R2ApiChatCaller(client=_Client(), operations=MagicMock())
        caller.answer = AsyncMock(return_value=response)
        context = _RequestContext()

        events = [
            event
            async for event in caller.stream(
                ChatOptions(question=response.question), context=context
            )
        ]

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertNotIn("answer", events[0].data)
        self.assertEqual(events[1].data, {"text": response.answer})
        self.assertEqual(events[-1].data["answer"], response.answer)
        self.assertIn("time_to_first_event_seconds", events[0].data["timings"])
        self.assertIn("time_to_first_event_seconds", events[-1].data["timings"])
        self.assertIn("time_to_first_token_seconds", events[-1].data["timings"])
        self.assertEqual(events[0].data["timings"]["retrieval_seconds"], 0.2)

    async def test_cancelled_buffered_r2_stream_emits_no_late_terminal_result(self) -> None:
        caller = R2ApiChatCaller(client=_Client(), operations=MagicMock())
        context = _RequestContext()

        async def cancel_before_result(*_args, **_kwargs):
            context._cancelled.set()
            return _response()

        caller.answer = cancel_before_result
        events = [
            event
            async for event in caller.stream(
                ChatOptions(question="Who opens the gate?"), context=context
            )
        ]

        self.assertEqual(events, [])


class _Client:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _LegacyEvidence:
    def __init__(self, evidence):
        self.evidence = evidence

    def retrieve(self, request, context):
        return self.evidence

    def reload_source(self, *, book_id: str, chunk_id: str):
        return None


class _Operations:
    def __init__(self, result):
        self.result = result
        self.question = None
        self.minimum_citation_count = None

    async def select_sources(self, **kwargs):
        self.question = kwargs["question"]
        self.minimum_citation_count = kwargs["minimum_citation_count"]
        self.remaining_seconds = kwargs["context"].remaining_seconds()
        return self.result


class _Context:
    def is_cancelled(self) -> bool:
        return False

    def remaining_seconds(self) -> float:
        return 30.0


def _response() -> ChatResponse:
    return ChatResponse(
        question="Who opens the gate?",
        answer="Mara opens the gate. [S1]",
        embedding_provider="ollama",
        embedding_model="all-minilm",
        generation_provider="grpc",
        generation_model="gpt-5.6-sol",
        retrieval_limit=3,
        candidate_count=1,
        filters={},
        sources=[],
        answer_capability="quality",
        retrieval_backend="sqlite",
        minimum_citation_count=1,
        timings=ChatTimings(
            query_embedding_seconds=0.1,
            retrieval_seconds=0.2,
            prompt_construction_seconds=0.0,
            generation_seconds=0.3,
            total_seconds=0.6,
        ),
    )
