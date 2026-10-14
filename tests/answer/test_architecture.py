import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))


class AnswerRuntimeArchitectureTests(unittest.TestCase):
    def test_domain_modules_do_not_import_adapters_or_delivery_implementations(self) -> None:
        domain_root = REPO_ROOT / "packages" / "librarian_answer"
        forbidden_roots = {
            "fastapi",
            "librarian_answer_adapters",
            "librarian_chat",
            "librarian_evaluation",
            "librarian_ingestion",
            "librarian_search",
            "librarian_storage",
        }
        violations: list[str] = []
        for path in sorted(domain_root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_roots:
                            violations.append(f"{path.name}: import {alias.name}")
                if module and module.split(".")[0] in forbidden_roots:
                    violations.append(f"{path.name}: from {module}")

        self.assertEqual(violations, [])
