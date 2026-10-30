from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from dataclasses import dataclass, field
from pathlib import Path

import grpc

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
)
from librarian_answer_adapters.grpc_generation import (
    GrpcGenerationGenerator,
    R2GenerationDeadlineExceeded,
)
from librarian_answer_adapters.worker_lifecycle import WorkerGenerationContext
from librarian_broker.execution import BrokerScheduler, ProviderExecutor
from librarian_broker.grpc_service import BrokerCredentials, create_broker_server
from librarian_chat.generation import ChatMessage
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import build_stack_contract
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

    async def test_rejects_an_elapsed_local_deadline_before_broker_admission(self) -> None:
        client = _Client()
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=_Context(remaining=0.0),
            default_operation=delivery_pb2.TAG_GENERATION,
        )

        with self.assertRaises(R2GenerationDeadlineExceeded):
            await asyncio.to_thread(
                generator.generate,
                [ChatMessage(role="user", content="Classify.")],
            )

        self.assertEqual(client.requests, [])

    def test_worker_context_distinguishes_shutdown_from_its_job_deadline(self) -> None:
        shutdown_requested = threading.Event()
        context = WorkerGenerationContext(
            shutdown_requested=shutdown_requested,
            deadline_seconds=30.0,
        )

        self.assertFalse(context.is_cancelled())
        self.assertGreater(context.remaining_seconds(), 0.0)
        shutdown_requested.set()
        self.assertTrue(context.is_cancelled())

    async def test_worker_shutdown_cancels_the_inflight_broker_call(self) -> None:
        client = _BlockingClient()
        shutdown_requested = threading.Event()
        generator = GrpcGenerationGenerator(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            context=WorkerGenerationContext(
                shutdown_requested=shutdown_requested,
                deadline_seconds=30.0,
            ),
            default_operation=delivery_pb2.TAG_GENERATION,
        )

        generation = asyncio.create_task(
            asyncio.to_thread(
                generator.generate,
                [ChatMessage(role="user", content="Classify.")],
            )
        )
        await client.started.wait()
        shutdown_requested.set()
        with self.assertRaises(asyncio.CancelledError):
            await generation
        self.assertTrue(client.cancelled)

    async def test_explicit_cancellation_cancels_live_generated_rpc_without_late_output(self) -> None:
        context = _CancellationContext()
        provider, server, client, generator = await _live_generator(context)
        try:
            generation = asyncio.create_task(
                asyncio.to_thread(
                    generator.generate,
                    [ChatMessage(role="user", content="Generate.")],
                )
            )
            await asyncio.wait_for(provider.started.wait(), timeout=1)
            context.cause = "explicit"
            with self.assertRaises(asyncio.CancelledError):
                await generation
            await asyncio.wait_for(provider.cancelled.wait(), timeout=1)
        finally:
            await client.close()
            await server.stop(0)

        self.assertEqual(provider.completed_outputs, 0)

    async def test_disconnect_cancellation_cancels_live_generated_rpc_without_late_output(self) -> None:
        context = _CancellationContext()
        provider, server, client, generator = await _live_generator(context)
        try:
            generation = asyncio.create_task(
                asyncio.to_thread(
                    generator.generate,
                    [ChatMessage(role="user", content="Generate.")],
                )
            )
            await asyncio.wait_for(provider.started.wait(), timeout=1)
            context.cause = "disconnect"
            with self.assertRaises(asyncio.CancelledError):
                await generation
            await asyncio.wait_for(provider.cancelled.wait(), timeout=1)
        finally:
            await client.close()
            await server.stop(0)

        self.assertEqual(provider.completed_outputs, 0)

    async def test_deadline_cancellation_maps_live_generated_rpc_to_typed_deadline(self) -> None:
        context = _CancellationContext()
        provider, server, client, generator = await _live_generator(context)
        try:
            generation = asyncio.create_task(
                asyncio.to_thread(
                    generator.generate,
                    [ChatMessage(role="user", content="Generate.")],
                )
            )
            await asyncio.wait_for(provider.started.wait(), timeout=1)
            context.cause = "deadline"
            context.remaining = 0.0
            with self.assertRaises(R2GenerationDeadlineExceeded):
                await generation
            await asyncio.wait_for(provider.cancelled.wait(), timeout=1)
        finally:
            await client.close()
            await server.stop(0)

        self.assertEqual(provider.completed_outputs, 0)

    async def test_elapsed_context_deadline_rejects_before_live_broker_admission(self) -> None:
        context = _CancellationContext()
        context.cause = "deadline"
        context.remaining = 0.0
        provider, server, client, generator = await _live_generator(context)
        try:
            with self.assertRaises(R2GenerationDeadlineExceeded):
                await asyncio.to_thread(
                    generator.generate,
                    [ChatMessage(role="user", content="Generate.")],
                )
        finally:
            await client.close()
            await server.stop(0)

        self.assertFalse(provider.started.is_set())
        self.assertEqual(provider.completed_outputs, 0)

    async def test_explicit_and_disconnect_reject_before_live_broker_admission(self) -> None:
        for cause in ("explicit", "disconnect"):
            with self.subTest(cause=cause):
                context = _CancellationContext()
                context.cause = cause
                provider, server, client, generator = await _live_generator(context)
                try:
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.to_thread(
                            generator.generate,
                            [ChatMessage(role="user", content="Generate.")],
                        )
                finally:
                    await client.close()
                    await server.stop(0)

                self.assertFalse(provider.started.is_set())
                self.assertEqual(provider.completed_outputs, 0)

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


class _BlockingClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def generate(self, _request, *, timeout):
        del timeout
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _CancellationContext:
    def __init__(self) -> None:
        self.cause: str | None = None
        self.remaining = 30.0

    def is_cancelled(self) -> bool:
        return self.cause is not None

    def cancellation_cause(self) -> str | None:
        return self.cause

    @property
    def was_disconnected(self) -> bool:
        return self.cause == "disconnect"

    def remaining_seconds(self) -> float:
        return 0.0 if self.cause is not None else self.remaining


class _LiveBlockingProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.completed_outputs = 0

    async def generate(self, request, *, timeout_seconds: float) -> tuple[str, str]:
        del timeout_seconds
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        self.completed_outputs += 1
        return "late output", request.model_id


async def _live_generator(
    context: _CancellationContext,
) -> tuple[
    _LiveBlockingProvider,
    grpc.aio.Server,
    GeneratedGrpcBrokerClient,
    GrpcGenerationGenerator,
]:
    contract = build_stack_contract(
        stack_release_sha="a" * 40,
        descriptor=b"generated cancellation adapter proof descriptor",
    )
    provider = _LiveBlockingProvider()
    server = create_broker_server(
        contract=contract,
        credentials=BrokerCredentials({"api": "api-token"}),
        scheduler=BrokerScheduler(
            provider,
            limits=build_broker_execution_limits(validation_reserve_seconds=0.01),
        ),
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    client = GeneratedGrpcBrokerClient.connect(
        target=f"127.0.0.1:{port}",
        contract=contract,
        principal="api",
        bearer_token="api-token",
    )
    await client.ensure_ready()
    return (
        provider,
        server,
        client,
        GrpcGenerationGenerator(
            client=client,
            model="fixture-model",
            event_loop=asyncio.get_running_loop(),
            context=context,
            default_operation=delivery_pb2.GENRE_GENERATION,
        ),
    )


class _SummaryGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[int, float]] = []

    def generate_for_operation(self, _messages, *, operation: int, timeout_seconds: float) -> str:
        self.calls.append((operation, timeout_seconds))
        return delivery_pb2.GenerationOperation.Name(operation)
