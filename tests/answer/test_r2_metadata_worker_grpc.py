"""Generated-gRPC proof for the R2 metadata-worker role."""

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
from librarian_metadata.jobs import (
    EnqueueMetadataJobsOptions,
    ProcessMetadataJobsOptions,
    enqueue_metadata_jobs,
    process_metadata_jobs,
)
from librarian_storage.storage import (
    BookRecord,
    BookSummaryRecord,
    SQLiteIngestionStore,
    utc_now,
)


class R2MetadataWorkerGrpcTests(unittest.IsolatedAsyncioTestCase):
    """Prove the metadata worker's durable jobs use its generated client only."""

    async def asyncSetUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_book_summary()
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"R2 metadata worker proof descriptor",
        )
        self.provider = _MetadataProvider()
        self.server = create_broker_server(
            contract=self.contract,
            credentials=BrokerCredentials({"metadata-worker": "metadata-token"}),
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

    async def test_durable_tag_and_genre_jobs_reach_provider_through_generated_grpc(self) -> None:
        self._enqueue_jobs()
        client = await self._ready_client()
        try:
            result = await asyncio.to_thread(
                process_metadata_jobs,
                ProcessMetadataJobsOptions(
                    database_url=self.database_url,
                    limit=2,
                    generator_factory=self._generator_factory(client, threading.Event()),
                ),
            )
        finally:
            await client.close()

        with SQLiteIngestionStore(self.database_path) as store:
            completed = store.list_metadata_jobs(status="completed")

        self.assertEqual(result.completed, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual([job.job_type for job in completed], ["tags", "genres"])
        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.TAG_GENERATION, delivery_pb2.GENRE_GENERATION],
        )

    async def test_metadata_credential_is_denied_before_provider_execution_for_summary(self) -> None:
        client = await self._ready_client()
        generator = self._generator(client, threading.Event(), delivery_pb2.TAG_GENERATION)
        try:
            with self.assertRaises(GrpcBrokerClientError) as raised:
                await asyncio.to_thread(
                    generator.generate_for_operation,
                    _messages(),
                    operation=delivery_pb2.BOOK_SUMMARIZATION,
                )
        finally:
            await client.close()

        self.assertEqual(raised.exception.status, grpc.StatusCode.PERMISSION_DENIED)
        self.assertEqual(raised.exception.error_code, delivery_pb2.OPERATION_DENIED)
        self.assertEqual(self.provider.operations, [])

    async def test_worker_generation_deadline_cancels_blocking_provider_without_late_result(self) -> None:
        client = await self._ready_client()
        self.provider.block = True
        generator = self._generator(client, threading.Event(), delivery_pb2.TAG_GENERATION)
        try:
            with self.assertRaises(R2GenerationDeadlineExceeded):
                await asyncio.to_thread(
                    generator.generate_for_operation,
                    _messages(),
                    operation=delivery_pb2.TAG_GENERATION,
                    timeout_seconds=0.1,
                )
            await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)
            self.provider.block = False
            self.assertEqual(
                await asyncio.to_thread(generator.generate, _messages()),
                _TAG_RESPONSE,
            )
        finally:
            await client.close()

        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.TAG_GENERATION, delivery_pb2.TAG_GENERATION],
        )
        self.assertEqual(generator.default_timeout_seconds, 30.0)

    async def test_shutdown_leaves_claimed_job_for_recovery_on_next_metadata_worker_run(self) -> None:
        self._enqueue_jobs(include_genres=False)
        client = await self._ready_client()
        shutdown_requested = threading.Event()
        self.provider.block = True
        try:
            interrupted = asyncio.create_task(
                asyncio.to_thread(
                    process_metadata_jobs,
                    ProcessMetadataJobsOptions(
                        database_url=self.database_url,
                        limit=1,
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
                running = store.list_metadata_jobs(status="running")
            self.assertEqual(len(running), 1)
            self.assertEqual(running[0].job_type, "tags")

            self.provider.block = False
            recovered = await asyncio.to_thread(
                process_metadata_jobs,
                ProcessMetadataJobsOptions(
                    database_url=self.database_url,
                    limit=1,
                    generator_factory=self._generator_factory(
                        client, threading.Event()
                    ),
                ),
            )
        finally:
            await client.close()

        with SQLiteIngestionStore(self.database_path) as store:
            completed = store.list_metadata_jobs(status="completed")

        self.assertEqual(recovered.completed, 1)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].attempts, 2)
        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.TAG_GENERATION, delivery_pb2.TAG_GENERATION],
        )

    async def _ready_client(self) -> GeneratedGrpcBrokerClient:
        client = GeneratedGrpcBrokerClient.connect(
            target=self.target,
            contract=self.contract,
            principal="metadata-worker",
            bearer_token="metadata-token",
        )
        await client.ensure_ready()
        return client

    def _generator_factory(
        self,
        client: GeneratedGrpcBrokerClient,
        shutdown_requested: threading.Event,
    ):
        loop = asyncio.get_running_loop()

        def factory(job_type: str) -> GrpcGenerationGenerator:
            operation = (
                delivery_pb2.TAG_GENERATION
                if job_type == "tags"
                else delivery_pb2.GENRE_GENERATION
            )
            return self._generator(client, shutdown_requested, operation, loop=loop)

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

    def _enqueue_jobs(self, *, include_genres: bool = True) -> None:
        self.assertEqual(
            enqueue_metadata_jobs(
                EnqueueMetadataJobsOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    source_summary_provider="fixture",
                    source_summary_model="fixture-model",
                    source_summary_detail="medium",
                    generation_provider="grpc",
                    generation_model="fixture-model",
                    include_genres=include_genres,
                )
            ),
            2 if include_genres else 1,
        )

    def _seed_book_summary(self) -> None:
        book = BookRecord(
            id="book-1",
            source_path="/fixtures/metadata.epub",
            relative_path="metadata.epub",
            file_hash="metadata-fixture",
            size_bytes=1,
            title="Fixture Metadata Book",
            authors=["Fixture Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        summary = BookSummaryRecord(
            id="summary-1",
            book_id="book-1",
            provider="fixture",
            model="fixture-model",
            detail="medium",
            source_hash="fixture",
            summary="Synthetic metadata summary.",
            chapter_summary_count=1,
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_book_summary(summary)


class _MetadataProvider(ProviderExecutor):
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
        response = (
            _TAG_RESPONSE
            if request.operation == delivery_pb2.TAG_GENERATION
            else _GENRE_RESPONSE
        )
        return response, request.model_id


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Generate fixture metadata.")]


_TAG_RESPONSE = '{"tags":[{"tag":"psychohistory","confidence":0.9,"rationale":"fixture"}]}'
_GENRE_RESPONSE = (
    '{"primary_genre":{"genre":"science fiction","confidence":0.9,'
    '"rationale":"fixture"},"secondary_genres":[]}'
)


if __name__ == "__main__":
    unittest.main()
