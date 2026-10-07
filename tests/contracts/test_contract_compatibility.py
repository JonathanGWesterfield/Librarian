"""Tests for the additive-only answer-delivery descriptor compatibility gate."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from google.protobuf import descriptor_pb2

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.compatibility import find_breaking_changes
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)


class ContractCompatibilityTests(unittest.TestCase):
    """Protect v1's additive-only evolution rule before broker implementation."""

    def test_current_descriptor_is_compatible_with_itself(self) -> None:
        descriptor = _current_descriptor()

        self.assertEqual(find_breaking_changes(descriptor, descriptor), [])

    def test_field_type_changes_and_required_fields_are_breaking(self) -> None:
        previous = _current_descriptor()
        current = _current_descriptor()
        chat_message = _messages(current)["ChatMessage"]
        chat_message.field[1].type = descriptor_pb2.FieldDescriptorProto.TYPE_BYTES
        chat_message.field[1].label = descriptor_pb2.FieldDescriptorProto.LABEL_REQUIRED

        changes = find_breaking_changes(previous, current)

        self.assertTrue(
            any(
                "message ChatMessage changed field content (2)" in change
                for change in changes
            )
        )
        self.assertIn(
            "message ChatMessage uses forbidden required field content", changes
        )

    def test_removed_messages_and_reused_reserved_enum_numbers_are_breaking(
        self,
    ) -> None:
        previous = _current_descriptor()
        current = _current_descriptor()
        del current.message_type[_message_index(current, "ErrorDetail")]
        operation = _enums(current)["GenerationOperation"]
        operation.value.add(name="FUTURE_OPERATION", number=10)

        changes = find_breaking_changes(previous, current)

        self.assertIn("message ErrorDetail was removed", changes)
        self.assertIn("enum GenerationOperation reused reserved number 10", changes)

    def test_cli_compares_the_checked_in_descriptor_with_a_git_revision(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/check_contract_breaking.py"),
                "--against",
                "HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("compatible with HEAD", completed.stdout)


def _current_descriptor() -> descriptor_pb2.FileDescriptorProto:
    descriptor = descriptor_pb2.FileDescriptorProto()
    descriptor.ParseFromString(delivery_pb2.DESCRIPTOR.serialized_pb)
    return descriptor


def _messages(
    descriptor: descriptor_pb2.FileDescriptorProto,
) -> dict[str, descriptor_pb2.DescriptorProto]:
    return {message.name: message for message in descriptor.message_type}


def _enums(
    descriptor: descriptor_pb2.FileDescriptorProto,
) -> dict[str, descriptor_pb2.EnumDescriptorProto]:
    return {enum.name: enum for enum in descriptor.enum_type}


def _message_index(descriptor: descriptor_pb2.FileDescriptorProto, name: str) -> int:
    return next(
        index
        for index, message in enumerate(descriptor.message_type)
        if message.name == name
    )
