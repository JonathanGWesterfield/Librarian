"""Keep the temporary R0 HTTP broker target explicit until M03 removes it."""

from __future__ import annotations

import json
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = (
    REPO_ROOT / "tests/fixtures/answer_delivery/v1/http_broker_target_exceptions.json"
)
RUNTIME_ROOTS = (REPO_ROOT / "apps", REPO_ROOT / "packages", REPO_ROOT / "scripts")
RUNTIME_SUFFIXES = frozenset({".json", ".ps1", ".py", ".sh", ".yaml", ".yml"})
IGNORED_PARTS = frozenset({"__pycache__", "dist", "node_modules"})
HTTP_BROKER_TARGET = re.compile(r"https?://codex-broker(?::\d+)?(?:/[^\s\"']*)?")


@dataclass(frozen=True, order=True)
class BrokerHttpTarget:
    source: str
    target: str


class BrokerHttpTargetExceptionTests(unittest.TestCase):
    """Prevent an unrecorded R0 HTTP broker path from reaching M03 migration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_inventory_has_one_versioned_m03_removal_exception(self) -> None:
        self.assertEqual(set(self.inventory), {"schema_version", "exceptions"})
        self.assertEqual(self.inventory["schema_version"], "v1")
        self.assertEqual(len(self.inventory["exceptions"]), 1)

        exception = self.inventory["exceptions"][0]
        self.assertEqual(
            set(exception),
            {
                "id",
                "source",
                "target",
                "rationale",
                "removal_milestone",
                "documentation",
            },
        )
        self.assertEqual(exception["id"], "r0-docker-codex-broker-config")
        self.assertEqual(exception["removal_milestone"], "M03")
        self.assertTrue(exception["rationale"])
        self.assertTrue(exception["documentation"].startswith("docs/answer-delivery/"))
        self.assertTrue((REPO_ROOT / exception["source"]).is_file())

    def test_every_runtime_http_broker_target_is_a_documented_exception(self) -> None:
        expected = [
            BrokerHttpTarget(source=entry["source"], target=entry["target"])
            for entry in self.inventory["exceptions"]
        ]

        self.assertEqual(_runtime_http_broker_targets(), expected)


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
    paths = [REPO_ROOT / "docker-compose.yml"]
    for root in RUNTIME_ROOTS:
        paths.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in RUNTIME_SUFFIXES
            and not (IGNORED_PARTS & set(path.relative_to(REPO_ROOT).parts))
        )
    return sorted(paths)
