"""Cancellation primitives shared by the R2 background-worker entry points."""

from __future__ import annotations

import asyncio
import signal
import threading
from time import monotonic


class WorkerShutdownRequested(Exception):
    """A worker received a shutdown signal while it owned an active RPC."""


class WorkerGenerationContext:
    """One bounded job budget plus the worker process shutdown signal.

    A job deadline is deliberately separate from process shutdown.  Deadline
    exhaustion is recorded as a failed job, while a shutdown cancels the
    in-flight RPC and leaves the durable job running for recovery on restart.
    """

    def __init__(self, *, shutdown_requested: threading.Event, deadline_seconds: float = 30.0):
        if deadline_seconds <= 0:
            raise ValueError("worker generation deadline must be greater than zero")
        self._shutdown_requested = shutdown_requested
        self._deadline_at = monotonic() + deadline_seconds

    def is_cancelled(self) -> bool:
        return self._shutdown_requested.is_set()

    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline_at - monotonic())


class WorkerShutdown:
    """Own the signal handlers that tell a standalone worker to stop."""

    def __init__(self, event_loop: asyncio.AbstractEventLoop) -> None:
        self.requested = threading.Event()
        self._event_loop = event_loop
        self._signals = (signal.SIGINT, signal.SIGTERM)
        self._previous_handlers = {
            shutdown_signal: signal.getsignal(shutdown_signal)
            for shutdown_signal in self._signals
        }
        for shutdown_signal in self._signals:
            event_loop.add_signal_handler(shutdown_signal, self.requested.set)

    def close(self) -> None:
        for shutdown_signal in self._signals:
            self._event_loop.remove_signal_handler(shutdown_signal)
            signal.signal(shutdown_signal, self._previous_handlers[shutdown_signal])
