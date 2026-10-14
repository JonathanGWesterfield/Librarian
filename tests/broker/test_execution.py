"""Deterministic scheduler and provider-cleanup tests for the gRPC broker."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_broker.execution import (
    BrokerAdmissionFull,
    BrokerScheduler,
    CodexSubprocessExecutor,
    ProviderExecutor,
)
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)


class BrokerExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_rejects_a_request_beyond_its_bounded_queue(self) -> None:
        provider = _BlockingProvider()
        scheduler = BrokerScheduler(
            provider,
            limits=build_broker_execution_limits(max_queued_requests=0),
        )
        first = asyncio.create_task(
            scheduler.execute(_request(), deadline_seconds=30)
        )
        await provider.started.wait()

        with self.assertRaises(BrokerAdmissionFull):
            await scheduler.execute(_request(), deadline_seconds=30)

        provider.release.set()
        await first

    async def test_cancelled_subprocess_execution_terminates_and_reaps_its_group(self) -> None:
        process = _FakeProcess()
        executor = CodexSubprocessExecutor(lambda request: ["codex", "exec"])
        with (
            patch(
                "librarian_broker.execution.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ),
            patch("librarian_broker.execution.os.killpg") as killpg,
        ):
            task = asyncio.create_task(
                executor.generate(_request(), timeout_seconds=30)
            )
            await process.communicating.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        killpg.assert_called_once_with(process.pid, __import__("signal").SIGTERM)
        self.assertGreaterEqual(process.wait_calls, 1)


class _BlockingProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, request, *, timeout_seconds):
        self.started.set()
        await self.release.wait()
        return "Fixture output.", "fixture-model"


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 1234
        self.returncode = None
        self.communicating = asyncio.Event()
        self._wait_complete = asyncio.Event()
        self.wait_calls = 0

    async def communicate(self, prompt):
        self.communicating.set()
        await asyncio.Event().wait()

    async def wait(self):
        self.wait_calls += 1
        self.returncode = -15
        self._wait_complete.set()


def _request() -> delivery_pb2.GenerateRequest:
    return delivery_pb2.GenerateRequest(
        request_id="10000000-0000-4000-8000-000000000001",
        correlation_id="execution-test",
        operation=delivery_pb2.CHAPTER_SUMMARIZATION,
        model_id="gpt-5.6-sol",
        messages=[delivery_pb2.ChatMessage(role=delivery_pb2.USER, content="Summarize.")],
        output_contract=delivery_pb2.PLAIN_TEXT_V1,
    )
