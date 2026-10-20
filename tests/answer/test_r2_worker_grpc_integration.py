from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer_adapters.grpc_broker import GeneratedGrpcBrokerClient
from librarian_answer_adapters.grpc_generation import GrpcGenerationGenerator
from librarian_answer_adapters.worker_lifecycle import WorkerGenerationContext
from librarian_broker.execution import BrokerScheduler, ProviderExecutor
from librarian_broker.grpc_service import BrokerCredentials, create_broker_server
from librarian_chat.generation import ChatMessage
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_evaluation.llm_judge import GrpcEvaluatorJudge
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import build_stack_contract


class R2WorkerGrpcIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercise both worker roles against a live generated gRPC listener."""

    async def asyncSetUp(self) -> None:
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"R2 worker integration descriptor",
        )
        self.provider = _RecordingProvider()
        self.server = create_broker_server(
            contract=self.contract,
            credentials=BrokerCredentials(
                {
                    "summary-worker": "summary-token",
                    "metadata-worker": "metadata-token",
                    "evaluator": "evaluator-token",
                }
            ),
            scheduler=BrokerScheduler(
                self.provider,
                limits=build_broker_execution_limits(),
            ),
        )
        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()
        self.target = f"127.0.0.1:{port}"

    async def asyncTearDown(self) -> None:
        await self.server.stop(0)

    async def test_summary_and_metadata_workers_use_only_their_authorized_operations(self) -> None:
        summary_client = self._client("summary-worker", "summary-token")
        metadata_client = self._client("metadata-worker", "metadata-token")
        await summary_client.ensure_ready()
        await metadata_client.ensure_ready()
        try:
            summary_generator = GrpcGenerationGenerator(
                client=summary_client,
                model="gpt-5.6-sol",
                event_loop=asyncio.get_running_loop(),
                context=WorkerGenerationContext(shutdown_requested=threading.Event()),
                default_operation=delivery_pb2.BOOK_SUMMARIZATION,
            )
            metadata_context = WorkerGenerationContext(shutdown_requested=threading.Event())
            tag_generator = GrpcGenerationGenerator(
                client=metadata_client,
                model="gpt-5.6-sol",
                event_loop=asyncio.get_running_loop(),
                context=metadata_context,
                default_operation=delivery_pb2.TAG_GENERATION,
            )
            genre_generator = GrpcGenerationGenerator(
                client=metadata_client,
                model="gpt-5.6-sol",
                event_loop=asyncio.get_running_loop(),
                context=metadata_context,
                default_operation=delivery_pb2.GENRE_GENERATION,
            )

            messages = [ChatMessage(role="user", content="Fixture request.")]
            await asyncio.to_thread(
                summary_generator.generate_for_operation,
                messages,
                operation=delivery_pb2.CHAPTER_SUMMARIZATION,
            )
            await asyncio.to_thread(summary_generator.generate, messages)
            await asyncio.to_thread(tag_generator.generate, messages)
            await asyncio.to_thread(genre_generator.generate, messages)
        finally:
            await summary_client.close()
            await metadata_client.close()

        self.assertEqual(
            self.provider.operations,
            [
                delivery_pb2.CHAPTER_SUMMARIZATION,
                delivery_pb2.BOOK_SUMMARIZATION,
                delivery_pb2.TAG_GENERATION,
                delivery_pb2.GENRE_GENERATION,
            ],
        )

    async def test_evaluator_uses_its_generated_client_for_judgement_only(self) -> None:
        client = self._client("evaluator", "evaluator-token")
        await client.ensure_ready()
        try:
            judge = GrpcEvaluatorJudge(
                client=client,
                model="gpt-5.6-sol",
                event_loop=asyncio.get_running_loop(),
                shutdown_requested=threading.Event(),
            )
            response = await asyncio.to_thread(judge.judge, "Judge the fixture answer.")
        finally:
            await client.close()

        self.assertEqual(response, "Fixture provider output.")
        self.assertEqual(self.provider.operations, [delivery_pb2.EVALUATOR_JUDGEMENT])

    def _client(self, principal: str, bearer_token: str) -> GeneratedGrpcBrokerClient:
        return GeneratedGrpcBrokerClient.connect(
            target=self.target,
            contract=self.contract,
            principal=principal,
            bearer_token=bearer_token,
        )


class _RecordingProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.operations: list[int] = []

    async def generate(self, request, *, timeout_seconds: float) -> tuple[str, str]:
        del timeout_seconds
        self.operations.append(request.operation)
        return "Fixture provider output.", request.model_id


if __name__ == "__main__":
    unittest.main()
