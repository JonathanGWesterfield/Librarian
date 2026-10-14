"""The gRPC-only R2 Codex broker process entrypoint.

This module is intentionally separate from ``main``.  ``main`` remains the
temporary R0 HTTP broker until the atomic M03 caller cutover retires it; an R2
image starts only this gRPC server and has no HTTP listener.
"""

from __future__ import annotations

import asyncio
import os
import signal
import stat
import sys
from collections.abc import Callable
from pathlib import Path

from librarian_contracts.broker_limits import build_broker_execution_limits
from librarian_contracts.broker_server_config import (
    BrokerServerConfigError,
    BrokerServerRuntimeConfig,
    load_broker_server_runtime_config,
)
from librarian_contracts.compose_security import BROKER_SECRET_NAMES
from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)
from librarian_contracts.stack_contract import (
    StackContract,
    StackContractError,
    load_stack_contract,
)
from librarian_logging import configure_logging

from librarian_broker.execution import (
    BrokerExecutionFailed,
    BrokerScheduler,
    CodexSubprocessExecutor,
)
from librarian_broker.grpc_service import BrokerCredentials, create_broker_server

BROKER_RUNTIME_CONFIG_PATH = Path("/config/librarian.json")
BROKER_SECRETS_DIRECTORY = Path("/run/secrets")
STACK_CONTRACT_PATH = Path("/app/librarian-stack-contract.json")
PROTO_DESCRIPTOR_PATH = Path("/app/proto/librarian/answer/v1/answer_delivery.pb")
GRPC_LISTEN_ADDRESS = "[::]:50051"
SHUTDOWN_DRAIN_SECONDS = 5


class BrokerStartupError(RuntimeError):
    """The R2 broker must refuse startup without its exact trusted inputs."""


def load_r2_broker_inputs() -> tuple[BrokerServerRuntimeConfig, BrokerCredentials, StackContract]:
    """Load the strict runtime document, all verifier secrets, and manifest."""

    try:
        runtime_config = load_broker_server_runtime_config(BROKER_RUNTIME_CONFIG_PATH)
    except BrokerServerConfigError as error:
        raise BrokerStartupError("R2 broker runtime configuration is invalid") from error
    try:
        contract = load_stack_contract(
            STACK_CONTRACT_PATH,
            descriptor=PROTO_DESCRIPTOR_PATH.read_bytes(),
        )
    except (OSError, StackContractError) as error:
        raise BrokerStartupError("R2 broker stack contract is unavailable or invalid") from error
    return runtime_config, BrokerCredentials(_load_broker_credentials()), contract


def _load_broker_credentials() -> dict[str, str]:
    credentials: dict[str, str] = {}
    for role, secret_name in BROKER_SECRET_NAMES.items():
        path = BROKER_SECRETS_DIRECTORY / secret_name
        credentials[role] = _read_secret(path)
    if len(set(credentials.values())) != len(credentials):
        raise BrokerStartupError("R2 broker credential material is invalid")
    return credentials


def _read_secret(path: Path) -> str:
    """Read exactly one regular, non-symlink Compose secret without logging it."""

    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise BrokerStartupError("R2 broker credential material is unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BrokerStartupError("R2 broker credential material is invalid")
        with os.fdopen(descriptor, "r", encoding="utf-8") as file:
            descriptor = -1
            value = file.read().strip()
    except (OSError, UnicodeError) as error:
        raise BrokerStartupError("R2 broker credential material is unavailable") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not value:
        raise BrokerStartupError("R2 broker credential material is invalid")
    return value


def _codex_command_factory(
    config: BrokerServerRuntimeConfig,
) -> Callable[[delivery_pb2.GenerateRequest], list[str]]:
    """Return a fixed-model provider command factory owned by this broker."""

    def command(request: delivery_pb2.GenerateRequest) -> list[str]:
        if request.model_id != config.model:
            raise BrokerExecutionFailed()
        return [
            "codex",
            "exec",
            "--model",
            config.model,
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "-",
        ]

    return command


async def serve() -> None:
    """Start the private gRPC server and drain it on a process signal."""

    config, credentials, contract = load_r2_broker_inputs()
    scheduler = BrokerScheduler(
        CodexSubprocessExecutor(_codex_command_factory(config)),
        limits=build_broker_execution_limits(),
    )
    server = create_broker_server(
        contract=contract,
        credentials=credentials,
        scheduler=scheduler,
    )
    if server.add_insecure_port(GRPC_LISTEN_ADDRESS) == 0:
        raise BrokerStartupError("R2 broker could not bind its private gRPC listener")

    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signal_name, stop_requested.set)
        except NotImplementedError:  # pragma: no cover - Windows does not run this image
            pass
    await server.start()
    try:
        await stop_requested.wait()
    finally:
        await server.stop(SHUTDOWN_DRAIN_SECONDS)


def main() -> int:
    """Run the gRPC-only R2 broker without exposing a legacy HTTP route."""

    # The R2 image deliberately mounts only the strict broker configuration,
    # which is not a ``LibrarianConfig`` document.  File logging resolves its
    # destination through that legacy application config, so keep this private
    # broker's startup logging on stdout only.
    configure_logging(file_enabled=False)
    try:
        asyncio.run(serve())
    except BrokerStartupError as error:
        # Keep diagnostics deliberately generic: all detailed secret and
        # manifest data are deployment material, not broker output.
        print(f"[librarian] {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
