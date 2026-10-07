"""Tests for the immutable release manifest used by the future gRPC handshake."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.stack_contract import (
    CONTRACT_MAJOR,
    StackContractError,
    build_stack_contract,
    load_stack_contract,
    parse_stack_contract,
    serialize_stack_contract,
)


class StackContractManifestTests(unittest.TestCase):
    """Keep release metadata strict, descriptor-bound, and reproducible."""

    def test_build_and_serialize_the_exact_four_field_contract(self) -> None:
        descriptor = b"canonical descriptor bytes"

        contract = build_stack_contract(
            stack_release_sha="a" * 40,
            descriptor=descriptor,
            contract_minor=3,
        )

        self.assertEqual(contract.contract_major, CONTRACT_MAJOR)
        self.assertEqual(contract.contract_minor, 3)
        self.assertEqual(
            contract.descriptor_sha256,
            hashlib.sha256(descriptor).hexdigest(),
        )
        self.assertEqual(
            serialize_stack_contract(contract),
            "{\n"
            '  "stack_release_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",\n'
            '  "contract_major": 1,\n'
            '  "contract_minor": 3,\n'
            f'  "descriptor_sha256": "{hashlib.sha256(descriptor).hexdigest()}"\n'
            "}\n",
        )

    def test_parser_rejects_extra_fields_bad_hashes_and_bad_versions(self) -> None:
        valid = {
            "stack_release_sha": "a" * 40,
            "contract_major": 1,
            "contract_minor": 0,
            "descriptor_sha256": "b" * 64,
        }
        cases = {
            "missing fields": {"stack_release_sha": "a"},
            "extra field": {**valid, "ignored": True},
            "uppercase release SHA": {**valid, "stack_release_sha": "A" * 40},
            "wrong major": {**valid, "contract_major": 2},
            "non-integer major": {**valid, "contract_major": 1.0},
            "boolean minor": {**valid, "contract_minor": True},
            "uppercase descriptor digest": {**valid, "descriptor_sha256": "B" * 64},
        }

        for description, payload in cases.items():
            with self.subTest(description=description), self.assertRaises(StackContractError):
                parse_stack_contract(json.dumps(payload))

        repeated_field = (
            '{"stack_release_sha":"' + "a" * 40 + '",'
            '"stack_release_sha":"' + "b" * 40 + '",'
            '"contract_major":1,"contract_minor":0,'
            '"descriptor_sha256":"' + "b" * 64 + '"}'
        )
        with self.assertRaisesRegex(StackContractError, "repeats field"):
            parse_stack_contract(repeated_field)

    def test_loader_rejects_a_manifest_for_a_different_descriptor(self) -> None:
        contract = build_stack_contract(
            stack_release_sha="b" * 40,
            descriptor=b"original descriptor",
        )

        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "librarian-stack-contract.json"
            manifest_path.write_text(serialize_stack_contract(contract), encoding="utf-8")

            self.assertEqual(
                load_stack_contract(manifest_path, descriptor=b"original descriptor"),
                contract,
            )

            with self.assertRaisesRegex(StackContractError, "does not match"):
                load_stack_contract(manifest_path, descriptor=b"different descriptor")

    def test_generator_writes_and_checks_the_canonical_manifest(self) -> None:
        descriptor_path = REPO_ROOT / "proto/librarian/answer/v1/answer_delivery.pb"
        generator = REPO_ROOT / "scripts/generate_stack_contract.py"

        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "librarian-stack-contract.json"
            command = [
                sys.executable,
                str(generator),
                "--stack-release-sha",
                "c" * 40,
                "--descriptor",
                str(descriptor_path),
                "--output",
                str(manifest_path),
            ]
            generated = subprocess.run(command, check=False, capture_output=True, text=True)
            checked = subprocess.run(
                [*command, "--check"], check=False, capture_output=True, text=True
            )

            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("Stack contract is current", checked.stdout)

            manifest_path.write_text("{}\n", encoding="utf-8")
            stale = subprocess.run(
                [*command, "--check"], check=False, capture_output=True, text=True
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("does not match", stale.stderr)
