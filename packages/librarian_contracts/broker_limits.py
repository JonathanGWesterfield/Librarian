"""Validated execution limits shared by the future gRPC broker and its tests.

M01 records the approved R2 defaults without starting a broker.  M03 supplies
the scheduler and subprocess lifecycle that consumes these values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_MAX_ACTIVE_PROCESSES = 1
DEFAULT_MAX_QUEUED_REQUESTS = 4
DEFAULT_ADMISSION_DEADLINE_SECONDS = 1.0
DEFAULT_OUTER_DEADLINE_SECONDS = 30.0
DEFAULT_VALIDATION_RESERVE_SECONDS = 2.0
DEFAULT_MAX_BUFFERED_EVENTS = 64
DEFAULT_SHUTDOWN_DRAIN_SECONDS = 5.0


class BrokerExecutionLimitsError(ValueError):
    """Broker execution settings that cannot safely bound work."""


@dataclass(frozen=True)
class BrokerExecutionLimits:
    """Validated bounds for one broker scheduler and its provider subprocesses."""

    max_active_processes: int
    max_queued_requests: int
    admission_deadline_seconds: float
    outer_deadline_seconds: float
    validation_reserve_seconds: float
    max_buffered_events: int
    shutdown_drain_seconds: float


def build_broker_execution_limits(
    *,
    max_active_processes: int = DEFAULT_MAX_ACTIVE_PROCESSES,
    max_queued_requests: int = DEFAULT_MAX_QUEUED_REQUESTS,
    admission_deadline_seconds: float = DEFAULT_ADMISSION_DEADLINE_SECONDS,
    outer_deadline_seconds: float = DEFAULT_OUTER_DEADLINE_SECONDS,
    validation_reserve_seconds: float = DEFAULT_VALIDATION_RESERVE_SECONDS,
    max_buffered_events: int = DEFAULT_MAX_BUFFERED_EVENTS,
    shutdown_drain_seconds: float = DEFAULT_SHUTDOWN_DRAIN_SECONDS,
) -> BrokerExecutionLimits:
    """Build limits while proving deadlines leave time for final validation."""

    limits = BrokerExecutionLimits(
        max_active_processes=max_active_processes,
        max_queued_requests=max_queued_requests,
        admission_deadline_seconds=admission_deadline_seconds,
        outer_deadline_seconds=outer_deadline_seconds,
        validation_reserve_seconds=validation_reserve_seconds,
        max_buffered_events=max_buffered_events,
        shutdown_drain_seconds=shutdown_drain_seconds,
    )
    _validate_limits(limits)
    return limits


def provider_execution_budget_seconds(
    limits: BrokerExecutionLimits,
    *,
    elapsed_seconds: float,
) -> float:
    """Return the remaining provider budget after preserving validation time.

    The outer gRPC deadline remains authoritative.  A non-positive result means
    the broker must fail before it starts a provider subprocess.
    """

    _validate_limits(limits)
    elapsed = _require_positive_or_zero_finite_float(elapsed_seconds, "elapsed_seconds")
    budget = limits.outer_deadline_seconds - elapsed - limits.validation_reserve_seconds
    if budget <= 0:
        raise BrokerExecutionLimitsError("no provider execution budget remains")
    return budget


def _validate_limits(limits: BrokerExecutionLimits) -> None:
    _require_positive_int(limits.max_active_processes, "max_active_processes")
    _require_non_negative_int(limits.max_queued_requests, "max_queued_requests")
    _require_positive_float(limits.admission_deadline_seconds, "admission_deadline_seconds")
    _require_positive_float(limits.outer_deadline_seconds, "outer_deadline_seconds")
    _require_positive_float(limits.validation_reserve_seconds, "validation_reserve_seconds")
    _require_positive_int(limits.max_buffered_events, "max_buffered_events")
    _require_positive_float(limits.shutdown_drain_seconds, "shutdown_drain_seconds")
    if limits.admission_deadline_seconds > limits.outer_deadline_seconds:
        raise BrokerExecutionLimitsError("admission_deadline_seconds exceeds outer_deadline_seconds")
    if limits.validation_reserve_seconds >= limits.outer_deadline_seconds:
        raise BrokerExecutionLimitsError(
            "validation_reserve_seconds must be less than outer_deadline_seconds"
        )


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BrokerExecutionLimitsError(f"{label} must be a positive integer")
    return value


def _require_non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BrokerExecutionLimitsError(f"{label} must be a non-negative integer")
    return value


def _require_positive_float(value: object, label: str) -> float:
    normalized = _require_positive_or_zero_finite_float(value, label)
    if normalized <= 0:
        raise BrokerExecutionLimitsError(f"{label} must be a positive finite number")
    return normalized


def _require_positive_or_zero_finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise BrokerExecutionLimitsError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise BrokerExecutionLimitsError(f"{label} must be a non-negative finite number")
    return normalized
