"""Explicit lifecycle seam for the future R2 API grounded-chat caller.

It is intentionally not installed into the active R0 application yet.  R2's
sanitized broker-client configuration cannot also supply the legacy API's
retrieval configuration, so activating it is a later configuration migration
that must move every caller atomically.
"""

from __future__ import annotations

from dataclasses import dataclass

from librarian_answer_adapters.grpc_broker import GeneratedGrpcBrokerClient
from librarian_answer_adapters.grpc_chat import GrpcChatOperations
from librarian_answer_adapters.r2_startup import open_r2_client


@dataclass
class R2ApiChatCaller:
    """One ready generated client and the three API-chat operation adapters."""

    client: GeneratedGrpcBrokerClient
    operations: GrpcChatOperations

    @classmethod
    async def open(cls, *, model_id: str) -> R2ApiChatCaller:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("gRPC chat operations require a model ID")
        client = await open_r2_client(expected_principal="api")
        try:
            return cls(client=client, operations=GrpcChatOperations(client, model_id))
        except Exception:
            await client.close()
            raise

    async def close(self) -> None:
        """Close the process-owned gRPC channel during API shutdown."""

        await self.client.close()
