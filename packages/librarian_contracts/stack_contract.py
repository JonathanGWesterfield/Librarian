"""Immutable release metadata for the answer-delivery gRPC handshake."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_MAJOR = 1
DEFAULT_CONTRACT_MINOR = 0
_RELEASE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_DESCRIPTOR_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_FIELD_NAMES = frozenset(
    {
        "stack_release_sha",
        "contract_major",
        "contract_minor",
        "descriptor_sha256",
    }
)


class StackContractError(ValueError):
    """Raised when immutable release metadata is malformed or mismatched."""


@dataclass(frozen=True)
class StackContract:
    """Release metadata shared by every image in one atomic R2 stack."""

    stack_release_sha: str
    contract_major: int
    contract_minor: int
    descriptor_sha256: str


def build_stack_contract(
    *,
    stack_release_sha: str,
    descriptor: bytes,
    contract_minor: int = DEFAULT_CONTRACT_MINOR,
) -> StackContract:
    """Build validated release metadata from the canonical raw descriptor bytes."""

    contract = StackContract(
        stack_release_sha=stack_release_sha,
        contract_major=CONTRACT_MAJOR,
        contract_minor=contract_minor,
        descriptor_sha256=hashlib.sha256(descriptor).hexdigest(),
    )
    _validate_stack_contract(contract)
    return contract


def parse_stack_contract(raw: str | bytes) -> StackContract:
    """Parse one strict, non-secret stack-contract JSON document."""

    try:
        decoded = json.loads(raw, object_pairs_hook=_reject_duplicate_fields)
    except (TypeError, json.JSONDecodeError) as error:
        raise StackContractError("stack contract must be valid JSON") from error

    if not isinstance(decoded, dict):
        raise StackContractError("stack contract must be a JSON object")
    if set(decoded) != _FIELD_NAMES:
        missing = sorted(_FIELD_NAMES - set(decoded))
        unexpected = sorted(set(decoded) - _FIELD_NAMES)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected fields: {', '.join(unexpected)}")
        raise StackContractError(
            "stack contract has invalid fields (" + "; ".join(details) + ")"
        )

    contract = StackContract(
        stack_release_sha=decoded["stack_release_sha"],
        contract_major=decoded["contract_major"],
        contract_minor=decoded["contract_minor"],
        descriptor_sha256=decoded["descriptor_sha256"],
    )
    _validate_stack_contract(contract)
    return contract


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for field, value in pairs:
        if field in decoded:
            raise StackContractError(f"stack contract repeats field: {field}")
        decoded[field] = value
    return decoded


def serialize_stack_contract(contract: StackContract) -> str:
    """Render canonical JSON so build output is deterministic and reviewable."""

    _validate_stack_contract(contract)
    return json.dumps(
        {
            "stack_release_sha": contract.stack_release_sha,
            "contract_major": contract.contract_major,
            "contract_minor": contract.contract_minor,
            "descriptor_sha256": contract.descriptor_sha256,
        },
        indent=2,
    ) + "\n"


def load_stack_contract(path: Path, *, descriptor: bytes) -> StackContract:
    """Load a manifest and reject it unless it names the supplied descriptor."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise StackContractError(f"could not read stack contract {path}: {error}") from error

    contract = parse_stack_contract(raw)
    expected_descriptor_sha256 = hashlib.sha256(descriptor).hexdigest()
    if contract.descriptor_sha256 != expected_descriptor_sha256:
        raise StackContractError(
            "stack contract descriptor_sha256 does not match the canonical descriptor"
        )
    return contract


def _validate_stack_contract(contract: StackContract) -> None:
    if not isinstance(contract.stack_release_sha, str) or not _RELEASE_SHA_PATTERN.fullmatch(
        contract.stack_release_sha
    ):
        raise StackContractError("stack_release_sha must be a 40-character lowercase Git SHA")
    if (
        not isinstance(contract.contract_major, int)
        or isinstance(contract.contract_major, bool)
        or contract.contract_major != CONTRACT_MAJOR
    ):
        raise StackContractError(f"contract_major must be {CONTRACT_MAJOR}")
    if (
        isinstance(contract.contract_minor, bool)
        or not isinstance(contract.contract_minor, int)
        or contract.contract_minor < 0
    ):
        raise StackContractError("contract_minor must be a non-negative integer")
    if not isinstance(contract.descriptor_sha256, str) or not _DESCRIPTOR_SHA256_PATTERN.fullmatch(
        contract.descriptor_sha256
    ):
        raise StackContractError(
            "descriptor_sha256 must be a 64-character lowercase SHA-256 digest"
        )
