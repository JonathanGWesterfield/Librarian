from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_evaluation.llm_judge import GrpcEvaluatorJudge


class R2EvaluatorScriptTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluator_owns_one_ready_client_and_uses_the_evaluator_principal(self) -> None:
        module = _load_script_module()
        client = SimpleNamespace(close=AsyncMock())
        shutdown = SimpleNamespace(requested=threading.Event(), close=Mock())
        expected_result = object()
        captured: dict[str, object] = {}

        def run_evaluation(args, *, judge):
            captured["args"] = args
            captured["judge"] = judge
            return expected_result

        with (
            patch.object(module, "open_r2_client", new=AsyncMock(return_value=client)) as open_client,
            patch.object(module, "WorkerShutdown", return_value=shutdown),
            patch.object(module, "_run_evaluation", side_effect=run_evaluation),
        ):
            result = await module._run_r2_evaluator(
                SimpleNamespace(llm_judge=True, judge_mode="enforcing"),
                model="gpt-5.6-sol",
            )

        self.assertIs(result, expected_result)
        open_client.assert_awaited_once_with(expected_principal="evaluator")
        client.close.assert_awaited_once()
        shutdown.close.assert_called_once()
        judge = captured["judge"]
        self.assertIsInstance(judge, GrpcEvaluatorJudge)
        self.assertIs(judge.client, client)
        self.assertEqual(judge.model, "gpt-5.6-sol")
        self.assertIs(judge.shutdown_requested, shutdown.requested)

    async def test_evaluator_shutdown_cancels_the_inflight_generated_rpc(self) -> None:
        client = _BlockingClient()
        shutdown_requested = threading.Event()
        judge = GrpcEvaluatorJudge(
            client=client,
            model="gpt-5.6-sol",
            event_loop=asyncio.get_running_loop(),
            shutdown_requested=shutdown_requested,
        )

        judgement = asyncio.create_task(asyncio.to_thread(judge.judge, "Judge this answer."))
        await client.started.wait()
        shutdown_requested.set()

        with self.assertRaises(asyncio.CancelledError):
            await judgement
        self.assertTrue(client.cancelled)


def _load_script_module():
    path = REPO_ROOT / "scripts" / "evaluate_retrieval.py"
    module_name = f"r2_evaluator_script_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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


if __name__ == "__main__":
    unittest.main()
