"""Bounded provider execution for the unary gRPC broker service."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass

from librarian_contracts.broker_limits import BrokerExecutionLimits
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)


class BrokerAdmissionFull(RuntimeError):
    """Raised when bounded FIFO admission cannot accept another request."""


class BrokerDeadlineExceeded(RuntimeError):
    """Raised when queueing or provider execution exhausts the RPC budget."""


class BrokerExecutionFailed(RuntimeError):
    """Raised without exposing provider diagnostics to the gRPC caller."""


@dataclass(frozen=True)
class BrokerExecution:
    """One bounded provider result with broker-owned timing metadata."""

    content: str
    provider_model_id: str
    queue_wait_ms: int
    execution_ms: int


class BrokerScheduler:
    """A FIFO, capacity-bounded scheduler with one cancellable provider owner."""

    def __init__(self, provider: ProviderExecutor, *, limits: BrokerExecutionLimits) -> None:
        self._provider = provider
        self._limits = limits
        self._active = asyncio.Semaphore(limits.max_active_processes)
        self._lock = asyncio.Lock()
        self._queued = 0

    async def execute(
        self,
        request: delivery_pb2.GenerateRequest,
        *,
        deadline_seconds: float | None,
    ) -> BrokerExecution:
        """Admit one request and reserve final-validation time before execution."""

        started = time.monotonic()
        queue_timeout = self._queue_timeout(deadline_seconds)
        async with self._lock:
            if self._active.locked() and self._queued >= self._limits.max_queued_requests:
                raise BrokerAdmissionFull()
            self._queued += 1
        try:
            await asyncio.wait_for(self._active.acquire(), timeout=queue_timeout)
        except TimeoutError as error:
            raise BrokerDeadlineExceeded() from error
        finally:
            async with self._lock:
                self._queued -= 1

        queue_wait_ms = _milliseconds_since(started)
        try:
            provider_budget = self._provider_budget(
                started=started, deadline_seconds=deadline_seconds
            )
            execution_started = time.monotonic()
            content, provider_model_id = await self._provider.generate(
                request, timeout_seconds=provider_budget
            )
            return BrokerExecution(
                content=content,
                provider_model_id=provider_model_id,
                queue_wait_ms=queue_wait_ms,
                execution_ms=_milliseconds_since(execution_started),
            )
        except TimeoutError as error:
            raise BrokerDeadlineExceeded() from error
        finally:
            self._active.release()

    def _queue_timeout(self, deadline_seconds: float | None) -> float:
        if deadline_seconds is None:
            return self._limits.admission_deadline_seconds
        return min(self._limits.admission_deadline_seconds, deadline_seconds)

    def _provider_budget(
        self, *, started: float, deadline_seconds: float | None
    ) -> float:
        outer_budget = self._limits.outer_deadline_seconds
        if deadline_seconds is not None:
            outer_budget = min(outer_budget, deadline_seconds)
        remaining = (
            outer_budget
            - (time.monotonic() - started)
            - self._limits.validation_reserve_seconds
        )
        if remaining <= 0:
            raise BrokerDeadlineExceeded()
        return remaining


class ProviderExecutor:
    """The provider boundary owned by a scheduler slot."""

    async def generate(
        self, request: delivery_pb2.GenerateRequest, *, timeout_seconds: float
    ) -> tuple[str, str]:
        raise NotImplementedError


class CodexSubprocessExecutor(ProviderExecutor):
    """Run one Codex process group and reap it on every terminal path."""

    def __init__(
        self,
        command_factory: Callable[[delivery_pb2.GenerateRequest], list[str]],
    ) -> None:
        self._command_factory = command_factory

    async def generate(
        self, request: delivery_pb2.GenerateRequest, *, timeout_seconds: float
    ) -> tuple[str, str]:
        command = self._command_factory(request)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            raise BrokerExecutionFailed() from error

        prompt = "\n\n".join(
            f"{delivery_pb2.MessageRole.Name(message.role)}:\n{message.content}"
            for message in request.messages
        ).encode("utf-8")
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(prompt), timeout=timeout_seconds
            )
        except (asyncio.CancelledError, TimeoutError):
            await _terminate_process_group(process)
            raise
        if process.returncode:
            raise BrokerExecutionFailed()
        content = stdout.decode("utf-8", errors="replace").strip()
        if not content:
            raise BrokerExecutionFailed()
        return content, request.model_id


async def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    """Terminate the owned session, escalate after three seconds, and reap it."""

    if process.returncode is not None:
        await process.wait()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
        return
    except TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


def _milliseconds_since(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
