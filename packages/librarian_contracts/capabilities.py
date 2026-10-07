"""Client-side validation for the authenticated broker capability handshake."""

from __future__ import annotations

from collections.abc import Iterable

from librarian_contracts.admission import OPERATION_POLICIES
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import (
    StackContract,
    StackContractError,
    serialize_stack_contract,
)

_CONTROL_PLANE_ONLY_PRINCIPAL = "compose-health"
_KNOWN_OPERATIONS = frozenset(OPERATION_POLICIES)


class CapabilitiesContractMismatch(ValueError):
    """A capability response that must keep the client unready."""


def build_capabilities_request(contract: StackContract) -> delivery_pb2.CapabilitiesRequest:
    """Build the exact release-bound request every generated client sends."""
    _validate_stack_contract(contract)
    return delivery_pb2.CapabilitiesRequest(
        contract_major=contract.contract_major,
        contract_minor=contract.contract_minor,
        descriptor_sha256=bytes.fromhex(contract.descriptor_sha256),
        stack_release_sha=contract.stack_release_sha,
    )


def required_operations_for_principal(principal: str) -> frozenset[int]:
    """Return the broker operations one authenticated principal must receive."""
    if principal == _CONTROL_PLANE_ONLY_PRINCIPAL:
        return frozenset()
    required = frozenset(
        operation
        for operation, policy in OPERATION_POLICIES.items()
        if principal in policy.permitted_principals
    )
    if not required:
        raise CapabilitiesContractMismatch("capability principal is not recognized")
    return required


def validate_capabilities_response(
    response: delivery_pb2.Capabilities,
    *,
    contract: StackContract,
    required_operations: Iterable[int],
) -> None:
    """Reject a response that cannot safely make a client ready.

    Authentication and status mapping belong to the future gRPC client and
    broker. This pure function makes the release, descriptor, range, and
    operation checks deterministic before either process exists.
    """
    _validate_stack_contract(contract)
    required = frozenset(required_operations)
    if not required <= _KNOWN_OPERATIONS:
        raise CapabilitiesContractMismatch("required operations are not recognized")
    returned = frozenset(response.operations)
    if not returned <= _KNOWN_OPERATIONS:
        raise CapabilitiesContractMismatch("capability response has an unknown operation")
    if response.contract_major != contract.contract_major:
        raise CapabilitiesContractMismatch("capability major does not match the stack contract")
    if response.min_contract_minor > response.max_contract_minor:
        raise CapabilitiesContractMismatch("capability minor range is invalid")
    if not response.min_contract_minor <= contract.contract_minor <= response.max_contract_minor:
        raise CapabilitiesContractMismatch("capability minor range does not include the stack contract")
    if response.descriptor_sha256 != bytes.fromhex(contract.descriptor_sha256):
        raise CapabilitiesContractMismatch("capability descriptor does not match the stack contract")
    if response.stack_release_sha != contract.stack_release_sha:
        raise CapabilitiesContractMismatch("capability release does not match the stack contract")
    if not required <= returned:
        raise CapabilitiesContractMismatch("capability response is missing a required operation")


def _validate_stack_contract(contract: StackContract) -> None:
    try:
        serialize_stack_contract(contract)
    except StackContractError as error:
        raise CapabilitiesContractMismatch("stack contract is invalid") from error
