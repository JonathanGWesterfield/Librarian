from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

import grpc
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer_adapters.grpc_broker import GrpcBrokerClientError
from librarian_answer_adapters.grpc_generation import (
    GrpcGenerationGenerator,
    R2GenerationDeadlineExceeded,
)
from librarian_chat.generation import ChatMessage
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_summarization.summarize import (
    _generate_book_summary,
    _generate_chunk_summary,
)


class GrpcGenerationGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_the_requested_operation_and_its_contract_on_the_shared_client(self) -> None:
        client = _Client()
        context = _Context()
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=context,
            default_operation=delivery_pb2.GENRE_GENERATION,
        )

        content = await asyncio.to_thread(
            generator.generate_for_operation,
            [ChatMessage(role="system", content="Classify the book.")],
            operation=delivery_pb2.RECOMMENDATION_SYNTHESIS,
            timeout_seconds=12.0,
        )

        self.assertEqual(content, "Generated output.")
        self.assertEqual(len(client.requests), 1)
        request = client.requests[0]
        self.assertEqual(request.operation, delivery_pb2.RECOMMENDATION_SYNTHESIS)
        self.assertEqual(request.output_contract, delivery_pb2.PLAIN_TEXT_V1)
        self.assertEqual(request.model_id, "gpt-5.6-sol")
        self.assertEqual(request.messages[0].role, delivery_pb2.SYSTEM)
        self.assertEqual(request.messages[0].content, "Classify the book.")
        self.assertFalse(request.HasField("evidence_snapshot"))
        self.assertEqual(client.timeouts, [12.0])

    async def test_caps_a_summary_call_at_the_broker_deadline(self) -> None:
        client = _Client()
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=_Context(remaining=80.0),
            default_operation=delivery_pb2.BOOK_SUMMARIZATION,
        )

        await asyncio.to_thread(
            generator.generate_for_operation,
            [ChatMessage(role="user", content="Summarize.")],
            operation=delivery_pb2.CHAPTER_SUMMARIZATION,
            timeout_seconds=240.0,
        )

        self.assertEqual(client.timeouts, [30.0])
        request = client.requests[0]
        self.assertEqual(request.operation, delivery_pb2.CHAPTER_SUMMARIZATION)
        self.assertEqual(request.output_contract, delivery_pb2.PLAIN_TEXT_V1)

    async def test_sequential_calls_consume_one_parent_request_budget(self) -> None:
        client = _Client()
        context = _Context(remaining=30.0)
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=context,
            default_operation=delivery_pb2.BOOK_SUMMARIZATION,
        )
        messages = [ChatMessage(role="user", content="Summarize.")]

        await asyncio.to_thread(generator.generate, messages)
        context.remaining = 0.5
        await asyncio.to_thread(generator.generate, messages)

        self.assertEqual(client.timeouts, [30.0, 0.5])

    async def test_rejects_a_broker_result_for_another_request(self) -> None:
        client = _Client(request_id="wrong-request")
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=_Context(),
            default_operation=delivery_pb2.GENRE_GENERATION,
        )

        with self.assertRaisesRegex(RuntimeError, "different request"):
            await asyncio.to_thread(
                generator.generate,
                [ChatMessage(role="user", content="Classify.")],
            )

    async def test_preserves_a_broker_deadline_as_a_typed_api_error(self) -> None:
        client = _Client(
            error=GrpcBrokerClientError(
                status=grpc.StatusCode.DEADLINE_EXCEEDED,
                error_code=delivery_pb2.EXECUTION_TIMEOUT,
            )
        )
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=_Context(),
            default_operation=delivery_pb2.RECOMMENDATION_SYNTHESIS,
        )

        with self.assertRaises(R2GenerationDeadlineExceeded):
            await asyncio.to_thread(
                generator.generate,
                [ChatMessage(role="user", content="Recommend.")],
            )

    def test_summary_helpers_select_chapter_and_book_operations(self) -> None:
        generator = _SummaryGenerator()
        messages = [ChatMessage(role="user", content="Summarize.")]

        self.assertEqual(
            _generate_chunk_summary(generator, messages, timeout_seconds=11.0),
            "CHAPTER_SUMMARIZATION",
        )
        self.assertEqual(
            _generate_book_summary(generator, messages, timeout_seconds=12.0),
            "BOOK_SUMMARIZATION",
        )
        self.assertEqual(
            generator.calls,
            [
                (delivery_pb2.CHAPTER_SUMMARIZATION, 11.0),
                (delivery_pb2.BOOK_SUMMARIZATION, 12.0),
            ],
        )


@dataclass
class _Client:
    request_id: str | None = None
    error: Exception | None = None
    requests: list = field(default_factory=list)
    timeouts: list[float | None] = field(default_factory=list)

    async def generate(self, request, *, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return delivery_pb2.GenerateResult(
            request_id=self.request_id or request.request_id,
            provider_model_id="gpt-5.6-sol",
            success=delivery_pb2.GenerationSuccess(content="Generated output."),
        )


class _Context:
    def __init__(self, *, remaining: float = 30.0) -> None:
        self.remaining = remaining

    def is_cancelled(self) -> bool:
        return False

    def remaining_seconds(self) -> float:
        return self.remaining


class _SummaryGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[int, float]] = []

    def generate_for_operation(self, _messages, *, operation: int, timeout_seconds: float) -> str:
        self.calls.append((operation, timeout_seconds))
        return delivery_pb2.GenerationOperation.Name(operation)
