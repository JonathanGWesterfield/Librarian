"""Generated-gRPC proof for the R2 summary-worker role."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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
from librarian_storage.storage import (
    BookRecord,
    ChunkRecord,
    SQLiteIngestionStore,
    SummaryJobRecord,
    utc_now,
)
from librarian_summarization.jobs import ProcessSummaryJobsOptions, process_summary_jobs


class R2SummaryWorkerGrpcTests(unittest.IsolatedAsyncioTestCase):
    """Prove durable summary work uses only its generated client operations."""

    async def asyncSetUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_book()
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"R2 summary worker proof descriptor",
        )
        self.provider = _SummaryProvider()
        self.server = create_broker_server(
            contract=self.contract,
            credentials=BrokerCredentials({"summary-worker": "summary-token"}),
            scheduler=BrokerScheduler(
                self.provider,
                limits=build_broker_execution_limits(validation_reserve_seconds=0.01),
            ),
        )
        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()
        self.target = f"127.0.0.1:{port}"

    async def asyncTearDown(self) -> None:
        await self.server.stop(0)
        self.temporary_directory.cleanup()

    async def test_durable_summary_job_reaches_provider_for_chapter_and_book_operations(self) -> None:
        self._seed_summary_job()
        client = await self._ready_client()
        try:
            result = await asyncio.to_thread(
                process_summary_jobs,
                ProcessSummaryJobsOptions(
                    database_url=self.database_url,
                    limit=1,
                    enqueue_metadata_jobs=False,
                    chunk_summary_timeout_seconds=30.0,
                    max_parallel_chunk_summaries=1,
                    generator_factory=self._generator_factory(client, threading.Event()),
                ),
            )
        finally:
            await client.close()

        with SQLiteIngestionStore(self.database_path) as store:
            completed = store.list_summary_jobs(status="completed")

        self.assertEqual(result.completed, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(completed), 1)
        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.CHAPTER_SUMMARIZATION, delivery_pb2.BOOK_SUMMARIZATION],
        )

    async def test_summary_credential_is_denied_before_provider_execution_for_tags(self) -> None:
        client = await self._ready_client()
        generator = self._generator(
            client, threading.Event(), delivery_pb2.BOOK_SUMMARIZATION
        )
        try:
            with self.assertRaises(GrpcBrokerClientError) as raised:
                await asyncio.to_thread(
                    generator.generate_for_operation,
                    _messages(),
                    operation=delivery_pb2.TAG_GENERATION,
                )
        finally:
            await client.close()

        self.assertEqual(raised.exception.status, grpc.StatusCode.PERMISSION_DENIED)
        self.assertEqual(raised.exception.error_code, delivery_pb2.OPERATION_DENIED)
        self.assertEqual(self.provider.operations, [])

    async def test_worker_generation_deadline_cancels_blocking_provider_without_late_result(self) -> None:
        client = await self._ready_client()
        self.provider.block = True
        generator = self._generator(
            client, threading.Event(), delivery_pb2.CHAPTER_SUMMARIZATION
        )
        try:
            with self.assertRaises(R2GenerationDeadlineExceeded):
                await asyncio.to_thread(
                    generator.generate_for_operation,
                    _messages(),
                    operation=delivery_pb2.CHAPTER_SUMMARIZATION,
                    timeout_seconds=0.1,
                )
            await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)
            self.provider.block = False
            self.assertEqual(
                await asyncio.to_thread(generator.generate, _messages()),
                "Fixture summary.",
            )
        finally:
            await client.close()

        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.CHAPTER_SUMMARIZATION, delivery_pb2.CHAPTER_SUMMARIZATION],
        )
        self.assertEqual(generator.default_timeout_seconds, 30.0)

    async def test_shutdown_leaves_claimed_summary_job_for_recovery_on_next_worker_run(self) -> None:
        self._seed_summary_job()
        client = await self._ready_client()
        shutdown_requested = threading.Event()
        self.provider.block = True
        try:
            interrupted = asyncio.create_task(
                asyncio.to_thread(
                    process_summary_jobs,
                    ProcessSummaryJobsOptions(
                        database_url=self.database_url,
                        limit=1,
                        enqueue_metadata_jobs=False,
                        chunk_summary_timeout_seconds=30.0,
                        max_parallel_chunk_summaries=1,
                        generator_factory=self._generator_factory(
                            client, shutdown_requested
                        ),
                    ),
                )
            )
            await asyncio.wait_for(self.provider.started.wait(), timeout=1)
            shutdown_requested.set()
            with self.assertRaises(asyncio.CancelledError):
                await interrupted
            await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)

            with SQLiteIngestionStore(self.database_path) as store:
                running = store.list_summary_jobs(status="running")
            self.assertEqual(len(running), 1)

            self.provider.block = False
            recovered = await asyncio.to_thread(
                process_summary_jobs,
                ProcessSummaryJobsOptions(
                    database_url=self.database_url,
                    limit=1,
                    enqueue_metadata_jobs=False,
                    chunk_summary_timeout_seconds=30.0,
                    max_parallel_chunk_summaries=1,
                    generator_factory=self._generator_factory(
                        client, threading.Event()
                    ),
                ),
            )
        finally:
            await client.close()

        with SQLiteIngestionStore(self.database_path) as store:
            completed = store.list_summary_jobs(status="completed")

        self.assertEqual(recovered.completed, 1)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].attempts, 2)
        self.assertEqual(
            self.provider.operations,
            [
                delivery_pb2.CHAPTER_SUMMARIZATION,
                delivery_pb2.CHAPTER_SUMMARIZATION,
                delivery_pb2.BOOK_SUMMARIZATION,
            ],
        )

    async def _ready_client(self) -> GeneratedGrpcBrokerClient:
        client = GeneratedGrpcBrokerClient.connect(
            target=self.target,
            contract=self.contract,
            principal="summary-worker",
            bearer_token="summary-token",
        )
        await client.ensure_ready()
        return client

    def _generator_factory(
        self,
        client: GeneratedGrpcBrokerClient,
        shutdown_requested: threading.Event,
    ):
        loop = asyncio.get_running_loop()

        def factory() -> GrpcGenerationGenerator:
            return self._generator(
                client,
                shutdown_requested,
                delivery_pb2.BOOK_SUMMARIZATION,
                loop=loop,
            )

        return factory

    def _generator(
        self,
        client: GeneratedGrpcBrokerClient,
        shutdown_requested: threading.Event,
        operation: int,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> GrpcGenerationGenerator:
        return GrpcGenerationGenerator(
            client=client,
            model="fixture-model",
            event_loop=loop or asyncio.get_running_loop(),
            context=WorkerGenerationContext(shutdown_requested=shutdown_requested),
            default_operation=operation,
        )

    def _seed_book(self) -> None:
        book = BookRecord(
            id="summary-book",
            source_path="/fixtures/summary.epub",
            relative_path="summary.epub",
            file_hash="summary-fixture",
            size_bytes=1,
            title="Fixture Summary Book",
            authors=["Fixture Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        chunk = ChunkRecord(
            id="summary-book:0",
            book_id="summary-book",
            chunk_index=0,
            text="Synthetic source text for summary generation.",
            character_count=45,
            token_estimate=8,
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [chunk])

    def _seed_summary_job(self) -> None:
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_summary_job(
                SummaryJobRecord(
                    id="summary-job-1",
                    book_id="summary-book",
                    provider="grpc",
                    model="fixture-model",
                    detail="medium",
                )
            )


class _SummaryProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.operations: list[int] = []
        self.block = False
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def generate(self, request, *, timeout_seconds: float) -> tuple[str, str]:
        del timeout_seconds
        self.operations.append(request.operation)
        if self.block:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        return "Fixture summary.", request.model_id


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Generate a fixture summary.")]


if __name__ == "__main__":
    unittest.main()
