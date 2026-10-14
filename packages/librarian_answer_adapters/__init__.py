"""Composition adapters for the in-process answer-runtime domain."""

from librarian_answer_adapters.legacy import (
    LegacyEvidenceRetriever,
    LegacyGenerationBroker,
    LegacySemanticGenerationBroker,
    LegacySentenceEvidenceRetriever,
    LegacySupportReviewer,
)

__all__ = [
    "LegacyEvidenceRetriever",
    "LegacyGenerationBroker",
    "LegacySemanticGenerationBroker",
    "LegacySentenceEvidenceRetriever",
    "LegacySupportReviewer",
]
