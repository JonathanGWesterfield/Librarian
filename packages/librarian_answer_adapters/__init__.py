"""Composition adapters for the in-process answer-runtime domain."""

from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
    GrpcRuntimeGenerationBroker,
)
from librarian_answer_adapters.legacy import (
    LegacyEvidenceRetriever,
    LegacyGenerationBroker,
    LegacySemanticGenerationBroker,
    LegacySentenceEvidenceRetriever,
    LegacySupportReviewer,
)

__all__ = [
    "GeneratedGrpcBrokerClient",
    "GrpcBrokerClientError",
    "GrpcRuntimeGenerationBroker",
    "LegacyEvidenceRetriever",
    "LegacyGenerationBroker",
    "LegacySemanticGenerationBroker",
    "LegacySentenceEvidenceRetriever",
    "LegacySupportReviewer",
]
