"""Tests for the bounded scheduler settings reserved for the R2 broker."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.broker_limits import (
    DEFAULT_ADMISSION_DEADLINE_SECONDS,
    DEFAULT_MAX_ACTIVE_PROCESSES,
    DEFAULT_MAX_BUFFERED_EVENTS,
    DEFAULT_MAX_QUEUED_REQUESTS,
    DEFAULT_OUTER_DEADLINE_SECONDS,
    DEFAULT_SHUTDOWN_DRAIN_SECONDS,
    DEFAULT_VALIDATION_RESERVE_SECONDS,
    BrokerExecutionLimitsError,
    build_broker_execution_limits,
    provider_execution_budget_seconds,
)


class BrokerExecutionLimitsTests(unittest.TestCase):
    """Every future broker must reserve final validation and cleanup time."""

    def test_defaults_match_the_approved_initial_broker_budget(self) -> None:
        limits = build_broker_execution_limits()

        self.assertEqual(limits.max_active_processes, DEFAULT_MAX_ACTIVE_PROCESSES)
        self.assertEqual(limits.max_queued_requests, DEFAULT_MAX_QUEUED_REQUESTS)
        self.assertEqual(limits.admission_deadline_seconds, DEFAULT_ADMISSION_DEADLINE_SECONDS)
        self.assertEqual(limits.outer_deadline_seconds, DEFAULT_OUTER_DEADLINE_SECONDS)
        self.assertEqual(limits.validation_reserve_seconds, DEFAULT_VALIDATION_RESERVE_SECONDS)
        self.assertEqual(limits.max_buffered_events, DEFAULT_MAX_BUFFERED_EVENTS)
        self.assertEqual(limits.shutdown_drain_seconds, DEFAULT_SHUTDOWN_DRAIN_SECONDS)

    def test_provider_budget_reserves_validation_from_the_authoritative_deadline(self) -> None:
        limits = build_broker_execution_limits()

        self.assertEqual(provider_execution_budget_seconds(limits, elapsed_seconds=0), 28.0)
        self.assertEqual(provider_execution_budget_seconds(limits, elapsed_seconds=27.5), 0.5)
        with self.assertRaisesRegex(BrokerExecutionLimitsError, "no provider execution budget"):
            provider_execution_budget_seconds(limits, elapsed_seconds=28)

    def test_rejects_unbounded_or_inconsistent_scheduler_settings(self) -> None:
        defaults = build_broker_execution_limits()
        cases = {
            "zero active processes": {"max_active_processes": 0},
            "negative queue": {"max_queued_requests": -1},
            "boolean buffered events": {"max_buffered_events": True},
            "infinite deadline": {"outer_deadline_seconds": float("inf")},
            "admission longer than outer": {
                "admission_deadline_seconds": defaults.outer_deadline_seconds + 1
            },
            "reserve consumes outer": {
                "validation_reserve_seconds": defaults.outer_deadline_seconds
            },
        }

        for description, overrides in cases.items():
            with self.subTest(description=description), self.assertRaises(BrokerExecutionLimitsError):
                build_broker_execution_limits(**overrides)

        invalid_limits = replace(defaults, max_buffered_events=0)
        with self.assertRaisesRegex(BrokerExecutionLimitsError, "max_buffered_events"):
            provider_execution_budget_seconds(invalid_limits, elapsed_seconds=0)
        with self.assertRaisesRegex(BrokerExecutionLimitsError, "elapsed_seconds"):
            provider_execution_budget_seconds(defaults, elapsed_seconds=float("nan"))


if __name__ == "__main__":
    unittest.main()
