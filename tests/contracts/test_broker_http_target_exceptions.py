"""Prove the retired owned HTTP broker has no source target left to invoke."""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOTS = (REPO_ROOT / "apps", REPO_ROOT / "packages", REPO_ROOT / "scripts")
COMPOSE_SOURCES = (REPO_ROOT / "docker-compose.yml", REPO_ROOT / "docker-compose.r2.yml")
RUNTIME_SUFFIXES = frozenset({".json", ".ps1", ".py", ".sh", ".yaml", ".yml"})
IGNORED_PARTS = frozenset({"__pycache__", "dist", "node_modules"})
HTTP_BROKER_TARGET = re.compile(r"https?://codex-broker(?::\d+)?(?:/[^\s\"']*)?")


@dataclass(frozen=True, order=True)
class BrokerHttpTarget:
    source: str
    target: str


class BrokerHttpTargetRetirementTests(unittest.TestCase):
    """M03 admits no owned HTTP fallback, exception, or listener target."""

    def test_no_runtime_source_can_target_the_retired_broker_listener(self) -> None:
        self.assertEqual(_runtime_http_broker_targets(), [])


def _runtime_http_broker_targets() -> list[BrokerHttpTarget]:
    targets: list[BrokerHttpTarget] = []
    for source_path in _runtime_source_paths():
        source = source_path.relative_to(REPO_ROOT).as_posix()
        contents = source_path.read_text(encoding="utf-8")
        targets.extend(
            BrokerHttpTarget(source=source, target=match.group(0))
            for match in HTTP_BROKER_TARGET.finditer(contents)
        )
    return targets


def _runtime_source_paths() -> list[Path]:
    paths = list(COMPOSE_SOURCES)
    for root in RUNTIME_ROOTS:
        paths.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in RUNTIME_SUFFIXES
            and not (IGNORED_PARTS & set(path.relative_to(REPO_ROOT).parts))
        )
    return sorted(paths)
