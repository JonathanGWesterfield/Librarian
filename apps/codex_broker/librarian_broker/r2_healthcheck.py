"""Authenticated in-container gRPC Health probe for the R2 broker image."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

HEALTH_SECRET_PATH = Path("/run/secrets/codex-broker-health")
HEALTH_TARGET = "127.0.0.1:50051"


def main() -> int:
    """Return non-zero unless the private gRPC service is authenticated and serving."""

    try:
        token = _read_health_secret()
        channel = grpc.insecure_channel(HEALTH_TARGET)
        try:
            response = health_pb2_grpc.HealthStub(channel).Check(
                health_pb2.HealthCheckRequest(),
                metadata=(("authorization", f"Bearer {token}"),),
                timeout=2,
            )
        finally:
            channel.close()
        return int(response.status != health_pb2.HealthCheckResponse.SERVING)
    except (OSError, UnicodeError, grpc.RpcError):
        return 1


def _read_health_secret() -> str:
    descriptor = os.open(HEALTH_SECRET_PATH, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("health secret is not a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8") as file:
            descriptor = -1
            token = file.read().strip()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not token:
        raise OSError("health secret is empty")
    return token


if __name__ == "__main__":
    raise SystemExit(main())
