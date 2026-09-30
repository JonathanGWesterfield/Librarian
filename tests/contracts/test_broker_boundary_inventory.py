"""Keep the M03 broker migration scope complete before any transport changes."""

from __future__ import annotations

import ast
import json
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "tests/fixtures/answer_delivery/v1/boundary_inventory.json"
ENTRYPOINT_TARGETS = frozenset(
    {
        "answer_question",
        "evaluate_answers_with_llm_judge",
        "generate_book_genres",
        "generate_book_tags",
        "prepare_answer_question",
        "process_metadata_jobs",
        "process_summary_jobs",
        "recommend_books",
        "run_metadata_job_worker",
        "run_summary_job_worker",
        "stream_answer_question",
        "summarize_book",
    }
)
EXPECTED_OPERATIONS = {
    "GROUNDED_SYNTHESIS",
    "SEMANTIC_SOURCE_SELECTION",
    "SUPPORT_REVIEW",
    "EVALUATOR_JUDGEMENT",
    "CHAPTER_SUMMARIZATION",
    "BOOK_SUMMARIZATION",
    "TAG_GENERATION",
    "GENRE_GENERATION",
    "RECOMMENDATION_SYNTHESIS",
}


@dataclass(frozen=True, order=True)
class CallSite:
    source: str
    callable: str
    target: str


class BrokerBoundaryInventoryTests(unittest.TestCase):
    """Make each current broker consumer a deliberate M03 migration input."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_inventory_has_the_expected_versioned_shape(self) -> None:
        self.assertEqual(
            set(self.inventory),
            {"schema_version", "surfaces", "api_entrypoints", "host_entrypoints"},
        )
        self.assertEqual(self.inventory["schema_version"], "v1")

        surface_ids = [surface["id"] for surface in self.inventory["surfaces"]]
        self.assertEqual(len(surface_ids), len(set(surface_ids)))
        self.assertEqual(
            {
                consumer["principal"]
                for surface in self.inventory["surfaces"]
                for consumer in surface["r2_consumers"]
            },
            {"api", "summary-worker", "metadata-worker", "evaluator"},
        )
        self.assertEqual(
            {
                operation
                for surface in self.inventory["surfaces"]
                for consumer in surface["r2_consumers"]
                for operation in consumer["operations"]
            },
            EXPECTED_OPERATIONS,
        )

        for surface in self.inventory["surfaces"]:
            factory_call = surface["factory_call"]
            self.assertEqual(set(factory_call), {"source", "callable", "factory"})
            self.assertTrue(factory_call["source"].endswith(".py"))
            self.assertTrue((REPO_ROOT / factory_call["source"]).is_file())
            self.assertTrue(factory_call["callable"])
            self.assertTrue(factory_call["factory"])
            self.assertTrue(surface["r2_consumers"])
            for consumer in surface["r2_consumers"]:
                self.assertEqual(set(consumer), {"principal", "operations"})
                self.assertTrue(consumer["operations"])

    def test_every_direct_legacy_factory_call_is_in_the_inventory(self) -> None:
        expected = {
            CallSite(
                source=surface["factory_call"]["source"],
                callable=surface["factory_call"]["callable"],
                target=surface["factory_call"]["factory"],
            )
            for surface in self.inventory["surfaces"]
        }

        self.assertEqual(_direct_factory_calls(), expected)

    def test_every_api_generation_entrypoint_is_in_the_inventory(self) -> None:
        expected = {
            CallSite(**entrypoint) for entrypoint in self.inventory["api_entrypoints"]
        }

        self.assertEqual(
            _entrypoint_calls([REPO_ROOT / "apps/api/librarian_api/main.py"]), expected
        )

    def test_every_host_generation_entrypoint_is_in_the_inventory(self) -> None:
        expected = {
            (entrypoint["source"], target)
            for entrypoint in self.inventory["host_entrypoints"]
            for target in entrypoint["targets"]
        }

        observed = _host_entrypoint_targets()
        self.assertEqual(observed, expected)


def _direct_factory_calls() -> set[CallSite]:
    calls: set[CallSite] = set()
    for root in (REPO_ROOT / "apps", REPO_ROOT / "packages", REPO_ROOT / "scripts"):
        for source_path in _python_source_paths(root):
            tree = ast.parse(
                source_path.read_text(encoding="utf-8"), filename=str(source_path)
            )
            generator_aliases, generator_modules = _configured_generator_aliases(tree)
            relative_source = source_path.relative_to(REPO_ROOT).as_posix()
            calls.update(
                _calls_to_factory(
                    tree,
                    source=relative_source,
                    factory="create_configured_generator",
                    aliases=generator_aliases,
                    module_aliases=generator_modules,
                )
            )
            calls.update(
                _calls_to_factory(
                    tree,
                    source=relative_source,
                    factory="DockerCodexBrokerJudge",
                    aliases={"DockerCodexBrokerJudge"},
                    module_aliases=set(),
                )
            )
    return calls


def _configured_generator_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    aliases: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "librarian_chat.generation"
        ):
            for alias in node.names:
                if alias.name == "create_configured_generator":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "librarian_chat.generation":
                    modules.add(alias.asname or "generation")
        elif isinstance(node, ast.ImportFrom) and node.module == "librarian_chat":
            for alias in node.names:
                if alias.name == "generation":
                    modules.add(alias.asname or alias.name)
    return aliases, modules


def _calls_to_factory(
    tree: ast.AST,
    *,
    source: str,
    factory: str,
    aliases: set[str],
    module_aliases: set[str],
) -> set[CallSite]:
    visitor = _CallVisitor(
        target_names=aliases,
        target_attributes={(module_alias, factory) for module_alias in module_aliases},
    )
    visitor.visit(tree)
    return {
        CallSite(source=source, callable=callable_name, target=factory)
        for callable_name in visitor.calls
    }


def _entrypoint_calls(paths: list[Path]) -> set[CallSite]:
    calls: set[CallSite] = set()
    for source_path in paths:
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"), filename=str(source_path)
        )
        visitor = _CallVisitor(
            target_names=set(ENTRYPOINT_TARGETS), target_attributes=set()
        )
        visitor.visit(tree)
        source = source_path.relative_to(REPO_ROOT).as_posix()
        for target, callable_names in visitor.calls_by_target.items():
            calls.update(
                CallSite(source=source, callable=callable_name, target=target)
                for callable_name in callable_names
            )
    return calls


def _host_entrypoint_targets() -> set[tuple[str, str]]:
    observed: set[tuple[str, str]] = set()
    for source_path in _python_source_paths(REPO_ROOT / "scripts"):
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"), filename=str(source_path)
        )
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for target in ENTRYPOINT_TARGETS & names:
            observed.add((source_path.relative_to(REPO_ROOT).as_posix(), target))
    return observed


def _python_source_paths(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


class _CallVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        target_names: set[str],
        target_attributes: set[tuple[str, str]],
    ) -> None:
        self.target_names = target_names
        self.target_attributes = target_attributes
        self.callable_stack: list[str] = []
        self.calls: set[str] = set()
        self.calls_by_target: dict[str, set[str]] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.callable_stack.append(node.name)
        self.generic_visit(node)
        self.callable_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.callable_stack.append(node.name)
        self.generic_visit(node)
        self.callable_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        target = _called_target(node.func, self.target_names, self.target_attributes)
        if target is not None:
            callable_name = (
                self.callable_stack[-1] if self.callable_stack else "<module>"
            )
            self.calls.add(callable_name)
            self.calls_by_target.setdefault(target, set()).add(callable_name)
        self.generic_visit(node)


def _called_target(
    node: ast.expr,
    target_names: set[str],
    target_attributes: set[tuple[str, str]],
) -> str | None:
    if isinstance(node, ast.Name) and node.id in target_names:
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and (node.value.id, node.attr) in target_attributes
    ):
        return node.attr
    return None
