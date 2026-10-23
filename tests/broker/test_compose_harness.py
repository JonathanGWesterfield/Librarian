"""Deterministic tests for the synthetic provider used by R2 Compose UAT."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import signal
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

HAS_GRPC = importlib.util.find_spec("grpc") is not None
if HAS_GRPC:
    from librarian_broker.compose_harness import (
        _CANCELLATION_PID_PATH,
        _FakeProvider,
        _request_for,
        _run_controlled_subprocess,
        _wait_for_cancellation_pids,
        _wait_for_process_exit,
    )
    from librarian_contracts.admission import OPERATION_POLICIES, validate_generate_request
    from librarian_contracts.generated.librarian.answer.v1 import (
        answer_delivery_pb2 as delivery_pb2,
    )


@unittest.skipUnless(HAS_GRPC, "grpcio is required for the broker Compose harness")
class ComposeHarnessTests(unittest.IsolatedAsyncioTestCase):
    def test_fixture_request_satisfies_every_v1_operation_contract(self) -> None:
        for operation in OPERATION_POLICIES:
            request = _request_for(operation=operation, model="fixture-model")
            validate_generate_request(request)
            self.assertEqual(request.output_contract, OPERATION_POLICIES[operation].output_contract)
            self.assertEqual(
                request.HasField("evidence_snapshot"),
                OPERATION_POLICIES[operation].evidence_required,
            )

    async def test_fake_provider_returns_only_tracked_synthetic_output(self) -> None:
        provider = _FakeProvider()
        request = _request_for(
            operation=delivery_pb2.CHAPTER_SUMMARIZATION,
            model="fixture-model",
        )

        content, model = await provider.generate(request, timeout_seconds=1)

        self.assertEqual(content, "synthetic compose provider output")
        self.assertEqual(model, "fixture-model")

    async def test_controlled_cancellation_process_reaps_its_child(self) -> None:
        request = _request_for(
            operation=delivery_pb2.CHAPTER_SUMMARIZATION,
            model="fixture-model",
        )
        task = asyncio.create_task(
            _run_controlled_subprocess(request, timeout_seconds=30)
        )
        parent_pid = child_pid = None
        try:
            parent_pid, child_pid = await _wait_for_cancellation_pids(_CANCELLATION_PID_PATH)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await _wait_for_process_exit(parent_pid)
            await _wait_for_process_exit(child_pid)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            for process_id in (parent_pid, child_pid):
                if process_id is None:
                    continue
                try:
                    os.kill(process_id, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            _CANCELLATION_PID_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
