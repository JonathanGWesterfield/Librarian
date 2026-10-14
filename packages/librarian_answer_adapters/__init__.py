"""Composition adapters for the in-process answer-runtime domain."""

from librarian_answer_adapters.legacy import (
    LegacyEvidenceRetriever,
    LegacyGenerationBroker,
    LegacySupportReviewer,
)

__all__ = [
    "LegacyEvidenceRetriever",
    "LegacyGenerationBroker",
    "LegacySupportReviewer",
]
