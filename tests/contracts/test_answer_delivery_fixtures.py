"""Validate the synthetic M01 answer-delivery fixture bank without model access."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT / "tests/fixtures/answer_delivery/v1/synthetic_answer_cases.json"
)
CASE_IDS = frozenset(
    {
        "point_fact",
        "bounded_explanation",
        "broad_synthesis",
        "insufficient_evidence",
        "wrong_scope",
        "source_changed",
        "malformed_provider_structure",
        "broker_unavailable",
        "deadline_exceeded",
        "queue_full",
        "cancelled",
        "oversized_provider_result",
        "pre_admission_rejections",
        "contract_mismatch",
    }
)
PUBLIC_EVENTS = frozenset(
    {
        "started",
        "evidence_candidates",
        "generation_started",
        "validation_started",
        "answer_validated",
        "completed",
        "failed",
        "cancelled",
    }
)
TERMINAL_EVENTS = frozenset({"completed", "failed", "cancelled"})
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AnswerDeliveryFixtureTests(unittest.TestCase):
    """Keep M01 fixtures comprehensive, synthetic, and implementation-ready."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.cases = {case["id"]: case for case in cls.fixture["cases"]}

    def test_fixture_bank_has_the_required_versioned_case_matrix(self) -> None:
        self.assertEqual(set(self.fixture), {"fixture_version", "cases"})
        self.assertEqual(self.fixture["fixture_version"], "v1")
        self.assertEqual(set(self.cases), CASE_IDS)
        self.assertEqual(len(self.cases), len(self.fixture["cases"]))

        request_ids: set[str] = set()
        for case in self.cases.values():
            request = case["request"]
            request_id = request["request_id"]
            self.assertRegex(request_id, UUID_PATTERN)
            request_ids.add(request_id)
            self.assertEqual(
                case["provider"]["expected_calls"],
                len(case["provider"]["responses"]),
            )
            for candidate in request["evidence_snapshot"]:
                self.assertRegex(candidate["source_sha256"], SHA256_PATTERN)
                self.assertTrue(candidate["body_text_eligible"])
        self.assertEqual(len(request_ids), len(self.cases))

    def test_each_public_event_sequence_is_safe_and_has_one_terminal(self) -> None:
        for case in self.cases.values():
            events = [entry["event"] for entry in case["event_sequence"]]
            expected_terminal = case["expected"]["terminal_event"]
            if expected_terminal == "pre_admission_rejection":
                self.assertEqual(events, [], case["id"])
                continue

            self.assertEqual(events[0], "started", case["id"])
            self.assertTrue(set(events) <= PUBLIC_EVENTS, case["id"])
            self.assertEqual(events[-1], expected_terminal, case["id"])
            self.assertEqual(
                sum(event in TERMINAL_EVENTS for event in events), 1, case["id"]
            )
            self.assertNotIn("token", events, case["id"])
            self.assertEqual(
                "answer_validated" in events,
                case["expected"].get("result", {}).get("outcome") == "answered",
                case["id"],
            )

    def test_answered_cases_have_distinct_body_text_citations_at_the_right_floor(
        self,
    ) -> None:
        expected_floors = {
            "point_fact": 1,
            "bounded_explanation": 2,
            "broad_synthesis": 10,
        }
        for case_id, expected_floor in expected_floors.items():
            case = self.cases[case_id]
            result = case["expected"]["result"]
            sources = result["sources"]
            self.assertEqual(result["outcome"], "answered")
            self.assertEqual(result["minimum_citation_count"], expected_floor)
            self.assertEqual(result["citation_count"], expected_floor)
            self.assertEqual(len(sources), expected_floor)
            self.assertEqual(
                len({source["source_id"] for source in sources}), expected_floor
            )
            self.assertTrue(all(source["content_type"] == "body" for source in sources))
            self.assertEqual(case["provider"]["expected_calls"], 1)

        self.assertEqual(
            self.cases["broad_synthesis"]["expected"]["result"]["citation_count"], 10
        )

    def test_refusal_and_source_change_cases_do_not_invent_citations(self) -> None:
        for case_id, outcome in {
            "insufficient_evidence": "insufficient_evidence",
            "wrong_scope": "insufficient_evidence",
            "source_changed": "source_changed",
        }.items():
            case = self.cases[case_id]
            result = case["expected"]["result"]
            self.assertEqual(case["provider"]["expected_calls"], 0)
            self.assertEqual(result["outcome"], outcome)
            self.assertEqual(result["citation_count"], 0)
            self.assertEqual(result["sources"], [])

        self.assertTrue(self.cases["wrong_scope"]["expected"]["whole_library_retry"])
        source_change = self.cases["source_changed"]["expected"]["source_change"]
        self.assertNotEqual(
            source_change["expected_revision"], source_change["actual_revision"]
        )
        self.assertNotEqual(
            source_change["expected_sha256"], source_change["actual_sha256"]
        )

    def test_failure_cancellation_and_pre_admission_outcomes_are_bounded(self) -> None:
        malformed = self.cases["malformed_provider_structure"]
        self.assertEqual(malformed["provider"]["expected_calls"], 2)
        self.assertEqual(
            [
                entry["attempt"]
                for entry in malformed["event_sequence"]
                if "attempt" in entry
            ],
            [1, 1, 2, 2],
        )
        self.assertEqual(
            malformed["expected"]["error"]["code"], "generation_unavailable"
        )

        expected_failures = {
            "broker_unavailable": ("UNAVAILABLE", "broker_unavailable"),
            "deadline_exceeded": ("DEADLINE_EXCEEDED", "deadline_exceeded"),
            "queue_full": ("RESOURCE_EXHAUSTED", "admission_full"),
        }
        for case_id, (grpc_status, error_code) in expected_failures.items():
            expected = self.cases[case_id]["expected"]
            self.assertEqual(expected["grpc_status"], grpc_status)
            self.assertEqual(expected["error"]["code"], error_code)

        cancelled = self.cases["cancelled"]
        self.assertEqual(cancelled["provider"]["expected_calls"], 1)
        self.assertEqual(cancelled["event_sequence"][-1]["event"], "cancelled")
        self.assertNotIn(
            "completed", [entry["event"] for entry in cancelled["event_sequence"]]
        )

        oversized_result = self.cases["oversized_provider_result"]
        self.assertEqual(oversized_result["provider"]["expected_calls"], 2)
        self.assertEqual(
            oversized_result["provider"]["responses"][0]["outcome"],
            "invalid_structured_output:TOO_LARGE",
        )
        self.assertEqual(oversized_result["expected"]["result"]["outcome"], "answered")
        self.assertEqual(
            [
                entry["attempt"]
                for entry in oversized_result["event_sequence"]
                if entry["event"] == "generation_started"
            ],
            [1, 2],
        )

        pre_admission = self.cases["pre_admission_rejections"]
        self.assertEqual(pre_admission["provider"]["expected_calls"], 0)
        self.assertEqual(
            {variant["id"] for variant in pre_admission["expected"]["variants"]},
            {
                "oversized_request",
                "oversized_message",
                "oversized_excerpt",
                "oversized_snapshot",
                "unknown_enum",
                "operation_output_mismatch",
            },
        )
        self.assertTrue(
            all(
                variant["grpc_status"] == "INVALID_ARGUMENT"
                for variant in pre_admission["expected"]["variants"]
            )
        )

        compatibility = self.cases["contract_mismatch"]
        self.assertEqual(compatibility["provider"]["expected_calls"], 0)
        self.assertEqual(
            {variant["id"] for variant in compatibility["expected"]["variants"]},
            {"major", "minor", "descriptor", "release_sha"},
        )
        self.assertTrue(
            all(
                variant["grpc_status"] == "FAILED_PRECONDITION"
                and variant["error_code"] == "CONTRACT_MISMATCH"
                for variant in compatibility["expected"]["variants"]
            )
        )
