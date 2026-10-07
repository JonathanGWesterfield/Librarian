"""Tests for broker startup capability request and response validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.capabilities import (
    CapabilitiesContractMismatch,
    build_capabilities_request,
    required_operations_for_principal,
    validate_capabilities_response,
)
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import build_stack_contract


class BrokerCapabilitiesTests(unittest.TestCase):
    """A broker response must match one immutable release before use."""

    def setUp(self) -> None:
        self.contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=b"canonical descriptor bytes",
            contract_minor=3,
        )

    def test_request_copies_all_immutable_manifest_fields(self) -> None:
        request = build_capabilities_request(self.contract)

        self.assertEqual(request.contract_major, 1)
        self.assertEqual(request.contract_minor, 3)
        self.assertEqual(request.descriptor_sha256.hex(), self.contract.descriptor_sha256)
        self.assertEqual(request.stack_release_sha, self.contract.stack_release_sha)

    def test_each_principal_requires_only_its_permitted_operations(self) -> None:
        expected = {
            "api": {
                delivery_pb2.GROUNDED_SYNTHESIS,
                delivery_pb2.SEMANTIC_SOURCE_SELECTION,
                delivery_pb2.SUPPORT_REVIEW,
                delivery_pb2.CHAPTER_SUMMARIZATION,
                delivery_pb2.BOOK_SUMMARIZATION,
                delivery_pb2.GENRE_GENERATION,
                delivery_pb2.RECOMMENDATION_SYNTHESIS,
            },
            "summary-worker": {
                delivery_pb2.CHAPTER_SUMMARIZATION,
                delivery_pb2.BOOK_SUMMARIZATION,
            },
            "metadata-worker": {
                delivery_pb2.TAG_GENERATION,
                delivery_pb2.GENRE_GENERATION,
            },
            "evaluator": {delivery_pb2.EVALUATOR_JUDGEMENT},
            "answer-runtime": {
                delivery_pb2.GROUNDED_SYNTHESIS,
                delivery_pb2.SEMANTIC_SOURCE_SELECTION,
                delivery_pb2.SUPPORT_REVIEW,
            },
            "compose-health": set(),
        }

        for principal, operations in expected.items():
            with self.subTest(principal=principal):
                self.assertEqual(required_operations_for_principal(principal), operations)

        with self.assertRaisesRegex(CapabilitiesContractMismatch, "not recognized"):
            required_operations_for_principal("unknown")

    def test_matching_response_with_additive_known_operations_is_accepted(self) -> None:
        response = _response(self.contract, operations=tuple(range(1, 10)))

        validate_capabilities_response(
            response,
            contract=self.contract,
            required_operations=required_operations_for_principal("api"),
        )

    def test_mismatches_unknown_operations_and_missing_permissions_are_rejected(self) -> None:
        required = required_operations_for_principal("api")
        cases = {
            "wrong major": _response(self.contract, contract_major=2),
            "inverted minor range": _response(
                self.contract,
                min_contract_minor=4,
                max_contract_minor=3,
            ),
            "minor not included": _response(
                self.contract,
                min_contract_minor=4,
                max_contract_minor=5,
            ),
            "wrong digest": _response(self.contract, descriptor_sha256=b"x" * 32),
            "wrong release": _response(self.contract, stack_release_sha="b" * 40),
            "unknown operation": _response(self.contract, operations=(99,)),
            "missing operation": _response(
                self.contract,
                operations=tuple(required - {delivery_pb2.SUPPORT_REVIEW}),
            ),
        }

        for description, response in cases.items():
            with self.subTest(description=description), self.assertRaises(
                CapabilitiesContractMismatch
            ):
                validate_capabilities_response(
                    response,
                    contract=self.contract,
                    required_operations=required,
                )

        with self.assertRaisesRegex(CapabilitiesContractMismatch, "not recognized"):
            validate_capabilities_response(
                _response(self.contract, operations=tuple(required)),
                contract=self.contract,
                required_operations=(99,),
            )


def _response(
    contract,
    *,
    contract_major: int | None = None,
    min_contract_minor: int | None = None,
    max_contract_minor: int | None = None,
    descriptor_sha256: bytes | None = None,
    stack_release_sha: str | None = None,
    operations: tuple[int, ...] | None = None,
) -> delivery_pb2.Capabilities:
    return delivery_pb2.Capabilities(
        contract_major=contract.contract_major if contract_major is None else contract_major,
        min_contract_minor=(
            contract.contract_minor if min_contract_minor is None else min_contract_minor
        ),
        max_contract_minor=(
            contract.contract_minor if max_contract_minor is None else max_contract_minor
        ),
        descriptor_sha256=(
            bytes.fromhex(contract.descriptor_sha256)
            if descriptor_sha256 is None
            else descriptor_sha256
        ),
        stack_release_sha=(
            contract.stack_release_sha if stack_release_sha is None else stack_release_sha
        ),
        operations=operations or (),
    )


if __name__ == "__main__":
    unittest.main()
