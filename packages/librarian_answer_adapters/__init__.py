"""Composition adapters for the in-process answer-runtime domain."""

from librarian_answer_adapters.grpc_broker import (
    GeneratedGrpcBrokerClient,
    GrpcBrokerClientError,
    GrpcRuntimeGenerationBroker,
)
from librarian_answer_adapters.grpc_chat import GrpcChatOperations
from librarian_answer_adapters.grpc_generation import (
    GrpcGenerationGenerator,
    R2GenerationDeadlineExceeded,
)
from librarian_answer_adapters.legacy import (
    LegacyEvidenceRetriever,
    LegacyGenerationBroker,
    LegacySemanticGenerationBroker,
    LegacySentenceEvidenceRetriever,
    LegacySupportReviewer,
)
from librarian_answer_adapters.public_events import (
    PublicAnswerEventSerializer,
    SseFrameTooLargeError,
    encode_sse_event,
)

__all__ = [
    "GeneratedGrpcBrokerClient",
    "GrpcBrokerClientError",
    "GrpcRuntimeGenerationBroker",
    "GrpcChatOperations",
    "GrpcGenerationGenerator",
    "R2GenerationDeadlineExceeded",
    "LegacyEvidenceRetriever",
    "LegacyGenerationBroker",
    "LegacySemanticGenerationBroker",
    "LegacySentenceEvidenceRetriever",
    "LegacySupportReviewer",
    "PublicAnswerEventSerializer",
    "SseFrameTooLargeError",
    "encode_sse_event",
]
