"""Generated-gRPC proof for the R2 evaluator role."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import grpc

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "codex_broker"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
)
from librarian_broker.execution import BrokerScheduler, ProviderExecutor
from librarian_broker.grpc_service import BrokerCredentials, create_broker_server
from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import build_stack_contract
from librarian_evaluation.llm_judge import GrpcEvaluatorJudge, LLMJudgeError


class R2EvaluatorGrpcTests(unittest.IsolatedAsyncioTestCase):
    """Prove the evaluator has one generated-RPC-only judgement path."""

    async def asyncSetUp(self) -> None:
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"R2 evaluator proof descriptor",
        )
        self.provider = _EvaluatorProvider()
        self.server = create_broker_server(
            contract=self.contract,
            credentials=BrokerCredentials(
                {
                    "evaluator": "evaluator-token",
                    "summary-worker": "summary-token",
                }
            ),
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

    async def test_evaluator_judge_uses_only_evaluator_judgement_verdict_rpc(self) -> None:
        client = await self._ready_client("evaluator", "evaluator-token")
        judge = self._judge(client, threading.Event())
        try:
            verdict = await asyncio.to_thread(judge.judge, "Judge the fixture answer.")
        finally:
            await client.close()

        self.assertEqual(verdict, _VERDICT)
        self.assertEqual(self.provider.operations, [delivery_pb2.EVALUATOR_JUDGEMENT])
        self.assertEqual(
            self.provider.output_contracts,
            [delivery_pb2.EVALUATOR_VERDICT_JSON_V1],
        )
        self.assertEqual(judge.provider, "grpc_codex_broker")

    async def test_wrong_principals_are_denied_before_provider_execution(self) -> None:
        summary_client = await self._ready_client("summary-worker", "summary-token")
        evaluator_client = await self._ready_client("evaluator", "evaluator-token")
        try:
            with self.assertRaises(GrpcBrokerClientError) as summary_denied:
                await summary_client.generate(
                    _request_for(delivery_pb2.EVALUATOR_JUDGEMENT), timeout=1
                )
            with self.assertRaises(GrpcBrokerClientError) as evaluator_denied:
                await evaluator_client.generate(
                    _request_for(delivery_pb2.BOOK_SUMMARIZATION), timeout=1
                )
        finally:
            await summary_client.close()
            await evaluator_client.close()

        for raised in (summary_denied, evaluator_denied):
            self.assertEqual(raised.exception.status, grpc.StatusCode.PERMISSION_DENIED)
            self.assertEqual(raised.exception.error_code, delivery_pb2.OPERATION_DENIED)
        self.assertEqual(self.provider.operations, [])

    async def test_shortened_evaluator_budget_cancels_provider_without_legacy_fallback(self) -> None:
        client = await self._ready_client("evaluator", "evaluator-token")
        self.provider.block = True
        judge = self._judge(client, threading.Event())
        try:
            with (
                patch("librarian_evaluation.llm_judge._GRPC_EVALUATOR_DEADLINE_SECONDS", 0.1),
                patch(
                    "librarian_evaluation.llm_judge.CodexJudge",
                    side_effect=AssertionError("legacy Codex judge must not be constructed"),
                ),
                patch(
                    "librarian_evaluation.llm_judge.OllamaJudge",
                    side_effect=AssertionError("local Ollama judge must not be constructed"),
                ),
                patch(
                    "librarian_evaluation.llm_judge.subprocess.run",
                    side_effect=AssertionError("legacy subprocess judge must not run"),
                ),
                patch(
                    "librarian_evaluation.llm_judge.request.urlopen",
                    side_effect=AssertionError("HTTP judge fallback must not run"),
                ),
                self.assertRaisesRegex(LLMJudgeError, "gRPC Codex broker judge"),
            ):
                await asyncio.to_thread(judge.judge, "Judge the fixture answer.")
            await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)
            self.provider.block = False
            self.assertEqual(
                await asyncio.to_thread(judge.judge, "Judge the fixture answer."),
                _VERDICT,
            )
        finally:
            await client.close()

        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.EVALUATOR_JUDGEMENT, delivery_pb2.EVALUATOR_JUDGEMENT],
        )
        self.assertEqual(_evaluator_budget_seconds(), 30.0)

    async def test_shutdown_cancels_active_judgement_and_fresh_judge_recovers(self) -> None:
        client = await self._ready_client("evaluator", "evaluator-token")
        shutdown_requested = threading.Event()
        self.provider.block = True
        judge = self._judge(client, shutdown_requested)
        try:
            active = asyncio.create_task(
                asyncio.to_thread(judge.judge, "Judge the fixture answer.")
            )
            await asyncio.wait_for(self.provider.started.wait(), timeout=1)
            shutdown_requested.set()
            with self.assertRaises(asyncio.CancelledError):
                await active
            await asyncio.wait_for(self.provider.cancelled.wait(), timeout=1)

            self.provider.block = False
            recovered = self._judge(client, threading.Event())
            self.assertEqual(
                await asyncio.to_thread(recovered.judge, "Judge the fixture answer."),
                _VERDICT,
            )
        finally:
            await client.close()

        self.assertEqual(
            self.provider.operations,
            [delivery_pb2.EVALUATOR_JUDGEMENT, delivery_pb2.EVALUATOR_JUDGEMENT],
        )

    async def _ready_client(
        self, principal: str, bearer_token: str
    ) -> GeneratedGrpcBrokerClient:
        client = GeneratedGrpcBrokerClient.connect(
            target=self.target,
            contract=self.contract,
            principal=principal,
            bearer_token=bearer_token,
        )
        await client.ensure_ready()
        return client

    def _judge(
        self,
        client: GeneratedGrpcBrokerClient,
        shutdown_requested: threading.Event,
    ) -> GrpcEvaluatorJudge:
        return GrpcEvaluatorJudge(
            client=client,
            model="fixture-model",
            event_loop=asyncio.get_running_loop(),
            shutdown_requested=shutdown_requested,
        )


class _EvaluatorProvider(ProviderExecutor):
    def __init__(self) -> None:
        self.operations: list[int] = []
        self.output_contracts: list[int] = []
        self.block = False
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def generate(self, request, *, timeout_seconds: float) -> tuple[str, str]:
        del timeout_seconds
        self.operations.append(request.operation)
        self.output_contracts.append(request.output_contract)
        if self.block:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        return _VERDICT, request.model_id


def _request_for(operation: int) -> delivery_pb2.GenerateRequest:
    request_id = str(uuid.uuid4())
    output_contract = {
        delivery_pb2.EVALUATOR_JUDGEMENT: delivery_pb2.EVALUATOR_VERDICT_JSON_V1,
        delivery_pb2.BOOK_SUMMARIZATION: delivery_pb2.PLAIN_TEXT_V1,
    }[operation]
    return delivery_pb2.GenerateRequest(
        request_id=request_id,
        correlation_id="evaluator-proof",
        operation=operation,
        model_id="fixture-model",
        output_contract=output_contract,
        messages=[delivery_pb2.ChatMessage(role=delivery_pb2.USER, content="Fixture")],
    )


def _evaluator_budget_seconds() -> float:
    from librarian_evaluation.llm_judge import _GRPC_EVALUATOR_DEADLINE_SECONDS

    return _GRPC_EVALUATOR_DEADLINE_SECONDS


_VERDICT = (
    '{"evidence_verdict":"supported","citation_relevance":"all_relevant",'
    '"missing_coverage":[],"unsupported_claims":[],"reason":"Fixture verdict."}'
)


if __name__ == "__main__":
    unittest.main()
