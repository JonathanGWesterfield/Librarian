"""Fail-closed R2 gRPC caller startup and executable wrapper.

The wrapper is used only by the separate atomic R2 Compose composition.  It
does not make the legacy R0 process an implicit gRPC client: it validates the
fixed sanitized config and secret mount, loads the immutable image manifest,
performs the authenticated compatibility handshake, then replaces itself with
the requested API, worker, or evaluator command.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from librarian_contracts.broker_client_preflight import (
    BrokerClientPreflightError,
    preflight_broker_client,
)
from librarian_contracts.runtime_config import CLIENT_CREDENTIAL_ROLES
from librarian_contracts.stack_contract import StackContractError, load_stack_contract

from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
)

STACK_CONTRACT_PATH = Path("/app/librarian-stack-contract.json")
PROTO_DESCRIPTOR_PATH = Path("/app/proto/librarian/answer/v1/answer_delivery.pb")
STARTUP_HANDSHAKE_TIMEOUT_SECONDS = 5.0


class R2StartupError(RuntimeError):
    """A safe startup failure that must stop a caller before it claims work."""


async def verify_r2_client_startup(*, expected_principal: str) -> None:
    """Validate local R2 admission and the remote release compatibility gate."""

    client = await open_r2_client(expected_principal=expected_principal)
    await client.close()


async def open_r2_client(*, expected_principal: str) -> GeneratedGrpcBrokerClient:
    """Open one ready process-owned R2 client for a caller composition root.

    The caller owns closing the returned channel.  Keeping this construction
    separate from the command-wrapper check lets a long-running API retain one
    channel/stub rather than creating a channel for each request.
    """

    if expected_principal not in CLIENT_CREDENTIAL_ROLES:
        raise R2StartupError("R2 startup principal is not a broker caller")
    try:
        preflight = preflight_broker_client()
    except BrokerClientPreflightError as error:
        raise R2StartupError("R2 broker client preflight failed") from error
    if preflight.admission.principal != expected_principal:
        raise R2StartupError("R2 startup principal does not match its runtime configuration")
    try:
        contract = load_stack_contract(
            STACK_CONTRACT_PATH,
            descriptor=PROTO_DESCRIPTOR_PATH.read_bytes(),
        )
    except (OSError, StackContractError) as error:
        raise R2StartupError("R2 stack contract is unavailable or invalid") from error
    runtime_config = preflight.runtime_config
    if (
        runtime_config.contract_major != contract.contract_major
        or runtime_config.contract_minor != contract.contract_minor
    ):
        raise R2StartupError(
            "R2 runtime contract does not match the immutable stack contract"
        )
    try:
        bearer_token = preflight.admission.credential_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise R2StartupError("R2 broker credential is unavailable") from error
    if not bearer_token:
        raise R2StartupError("R2 broker credential is unavailable")

    client = GeneratedGrpcBrokerClient.connect(
        target=preflight.runtime_config.target,
        contract=contract,
        principal=preflight.admission.principal,
        bearer_token=bearer_token,
    )
    try:
        await client.ensure_ready(timeout=STARTUP_HANDSHAKE_TIMEOUT_SECONDS)
    except GrpcBrokerClientError as error:
        await client.close()
        raise R2StartupError("R2 broker capability handshake failed") from error
    return client


def main(argv: list[str] | None = None) -> int:
    """Handshake, then replace this wrapper with an R2 caller process."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--principal", required=True, choices=sorted(CLIENT_CREDENTIAL_ROLES))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        parser.error("a caller command is required after --")
    try:
        asyncio.run(verify_r2_client_startup(expected_principal=args.principal))
    except R2StartupError as error:
        print(f"[librarian] {error}", file=sys.stderr)
        return 2
    os.execvp(command[0], command)
    return 127  # pragma: no cover - os.execvp either replaces us or raises


if __name__ == "__main__":
    raise SystemExit(main())
