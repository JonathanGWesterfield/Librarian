import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/verify_compose.py"


class VerifyComposeScriptTests(unittest.TestCase):
    def test_main_seeds_runtime_api_indexes_fixture_and_evaluates_hybrid_api(self) -> None:
        """Verify the one-shot harness wires its three live system boundaries."""
        module = _load_script_module()
        report_path = Path("/tmp/librarian-compose-verification.json")
        markdown_path = Path("/tmp/librarian-compose-verification.md")

        def write_report(command, *, check):
            self.assertTrue(check)
            self.assertIn("--api-url", command)
            self.assertIn("http://api:8000", command)
            report_path.write_text(
                json.dumps(
                    {"retrieval": {"aggregate": {"hit_rate_at_k": {"1": 1.0}}}}
                ),
                encoding="utf-8",
            )

        try:
            with (
                patch.object(module, "_post_json", return_value={}) as post_json,
                patch.object(
                    module,
                    "index_chunks",
                    return_value=SimpleNamespace(documents_indexed=2),
                ) as index_chunks,
                patch.object(module.subprocess, "run", side_effect=write_report),
            ):
                result = module.main(
                    [
                        "--api-url",
                        "http://api:8000",
                        "--books-dir",
                        "/books",
                        "--database-url",
                        "sqlite:////verify-data/librarian.db",
                        "--opensearch-url",
                        "http://opensearch:9200",
                        "--ollama-base-url",
                        "http://ollama:11434",
                    ]
                )
        finally:
            report_path.unlink(missing_ok=True)
            markdown_path.unlink(missing_ok=True)

        self.assertEqual(result, 0)
        self.assertEqual(post_json.call_args.args[0], "http://api:8000/ingestion/run")
        self.assertEqual(post_json.call_args.args[1]["books_dir"], "/books")
        self.assertTrue(post_json.call_args.args[1]["embed_chunks"])
        self.assertEqual(index_chunks.call_args.args[0].opensearch_url, "http://opensearch:9200")
        self.assertTrue(index_chunks.call_args.args[0].reset)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("verify_compose_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
