"""Evidence snapshot construction and source-of-truth freshness checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from librarian_answer.models import EvidenceSnapshot, SourceRecord


class SourceFreshness(str, Enum):
    CURRENT = "current"
    SOURCE_CHANGED = "source_changed"


@dataclass(frozen=True)
class SourceReloadResult:
    """The outcome of reloading a single cited evidence candidate."""

    status: SourceFreshness
    source: SourceRecord | None = None

    @property
    def is_current(self) -> bool:
        return self.status is SourceFreshness.CURRENT


SourceReloader = Callable[[str, str], Optional[SourceRecord]]


def reload_snapshot_source(
    snapshot: EvidenceSnapshot, reloader: SourceReloader
) -> SourceReloadResult:
    """Reload one candidate and require exact revision and content identity.

    The source may have been deleted, re-ingested, or edited after retrieval.
    Any such change produces the domain outcome ``source_changed`` so callers
    must discard the in-flight answer instead of attaching a citation to the
    replacement text.
    """

    source = reloader(snapshot.book_id, snapshot.chunk_id)
    if source is None or source.book_id != snapshot.book_id:
        return SourceReloadResult(SourceFreshness.SOURCE_CHANGED)
    if (
        source.source_revision != snapshot.source_revision
        or source.content_sha256 != snapshot.source_sha256
    ):
        return SourceReloadResult(SourceFreshness.SOURCE_CHANGED, source)
    return SourceReloadResult(SourceFreshness.CURRENT, source)


def reload_citation_sources(
    snapshots: tuple[EvidenceSnapshot, ...], reloader: SourceReloader
) -> SourceFreshness:
    """Return ``source_changed`` when any final citation no longer matches."""

    for snapshot in snapshots:
        if not reload_snapshot_source(snapshot, reloader).is_current:
            return SourceFreshness.SOURCE_CHANGED
    return SourceFreshness.CURRENT
