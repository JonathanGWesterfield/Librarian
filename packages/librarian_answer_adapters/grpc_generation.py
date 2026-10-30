"""Synchronous generation facade over the process-owned R2 gRPC client.

The established API summary, genre, and recommendation workflows are
synchronous because they coordinate SQLite cache writes and, for summaries,
parallel section work.  This adapter deliberately keeps that local work in
those workflows while scheduling each provider execution on the API process's
single ready ``grpc.aio`` channel.  It never constructs a legacy generator or
another channel.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

import grpc
from librarian_answer.ports import resolve_cancellation_cause
from librarian_contracts.admission import OPERATION_POLICIES
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)

from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
    _await_generation_with_context,
)

_ROLE_BY_NAME = {
    "system": delivery_pb2.SYSTEM,
    "user": delivery_pb2.USER,
    "assistant": delivery_pb2.ASSISTANT,
}
_BROKER_MAX_DEADLINE_SECONDS = 30.0


class R2GenerationDeadlineExceeded(RuntimeError):
    """The broker exhausted the caller's generation deadline."""


class GenerationContext(Protocol):
    """The cancellation and deadline view needed by a generated RPC."""

    def is_cancelled(self) -> bool:
        ...

    def remaining_seconds(self) -> float | None:
        ...


@dataclass(frozen=True)
class GrpcGenerationGenerator:
    """Use a generated client where existing synchronous generators are expected."""

    client: GeneratedGrpcBrokerClient
    model: str
    event_loop: asyncio.AbstractEventLoop
    context: GenerationContext
    default_operation: int
    default_timeout_seconds: float = _BROKER_MAX_DEADLINE_SECONDS
    provider: str = "grpc"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("gRPC generation requires a model ID")
        if self.default_operation not in OPERATION_POLICIES:
            raise ValueError("gRPC generation operation is not supported by v1")
        if self.default_timeout_seconds <= 0:
            raise ValueError("gRPC generation deadline must be greater than zero")

    def generate(self, messages, *, response_format: str | None = None) -> str:
        """Generate through this facade's default R2 operation.

        ``response_format`` is accepted for compatibility with the local
        generator protocol.  The operation's protobuf output contract is the
        authoritative structured-output declaration.
        """

        del response_format
        return self.generate_for_operation(messages, operation=self.default_operation)

    def generate_for_operation(
        self,
        messages,
        *,
        operation: int,
        timeout_seconds: float | None = None,
    ) -> str:
        """Run one provider request with the operation's exact v1 contract."""

        if operation not in OPERATION_POLICIES:
            raise ValueError("gRPC generation operation is not supported by v1")
        cancellation_cause = resolve_cancellation_cause(self.context)
        if cancellation_cause == "deadline":
            raise R2GenerationDeadlineExceeded("gRPC generation deadline elapsed")
        if cancellation_cause is not None:
            raise asyncio.CancelledError("API generation was cancelled before broker admission")
        requested_timeout = (
            self.default_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        if requested_timeout <= 0:
            raise ValueError("gRPC generation deadline must be greater than zero")
        deadline = min(requested_timeout, _BROKER_MAX_DEADLINE_SECONDS)
        remaining = self.context.remaining_seconds()
        if remaining is not None:
            deadline = min(deadline, remaining)
        if deadline <= 0:
            raise R2GenerationDeadlineExceeded("gRPC generation deadline elapsed")

        future = asyncio.run_coroutine_threadsafe(
            self._generate(messages, operation=operation, timeout_seconds=deadline),
            self.event_loop,
        )
        try:
            # The coroutine watches browser cancellation and the gRPC deadline.
            # This margin only lets the worker receive that terminal state.
            return future.result(timeout=deadline + 0.25)
        except FutureCancelledError as error:
            # ``run_coroutine_threadsafe`` translates asyncio cancellation to
            # ``concurrent.futures.CancelledError`` at this synchronous
            # boundary. Convert it back so a worker shutdown can leave its
            # claimed job for normal restart recovery.
            if self.context.is_cancelled():
                raise asyncio.CancelledError("gRPC generation was cancelled") from error
            raise RuntimeError("gRPC generation was cancelled unexpectedly") from error
        except FutureTimeoutError as error:
            future.cancel()
            raise RuntimeError("gRPC generation did not finish before its deadline") from error

    async def _generate(self, messages, *, operation: int, timeout_seconds: float) -> str:
        policy = OPERATION_POLICIES[operation]
        request_id = str(uuid4())
        request = delivery_pb2.GenerateRequest(
            request_id=request_id,
            correlation_id=request_id,
            operation=operation,
            model_id=self.model,
            output_contract=policy.output_contract,
            messages=[
                delivery_pb2.ChatMessage(
                    role=_message_role(message),
                    content=message.content,
                )
                for message in messages
            ],
        )
        try:
            result = await _await_generation_with_context(
                self.client.generate(request, timeout=timeout_seconds), self.context
            )
        except asyncio.CancelledError:
            # Request contexts distinguish a browser/adapter abort from an
            # elapsed deadline.  Legacy worker contexts resolve a cancellation
            # to ``explicit``, preserving their existing shutdown behavior.
            if resolve_cancellation_cause(self.context) == "deadline":
                raise R2GenerationDeadlineExceeded(
                    "gRPC generation deadline elapsed"
                ) from None
            raise
        except GrpcBrokerClientError as error:
            if error.status is grpc.StatusCode.DEADLINE_EXCEEDED:
                raise R2GenerationDeadlineExceeded(
                    "gRPC generation deadline elapsed"
                ) from error
            raise
        if result.request_id != request_id:
            raise RuntimeError("broker returned a result for a different request")
        if result.WhichOneof("outcome") != "success":
            raise RuntimeError("broker returned invalid generated output")
        return result.success.content


def _message_role(message: object) -> int:
    role = getattr(message, "role", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str):
        raise ValueError("gRPC generation messages must contain text")
    try:
        return _ROLE_BY_NAME[role]
    except KeyError as error:
        raise ValueError("gRPC generation message role is not a v1 role") from error
