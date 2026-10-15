from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_contracts.generated.librarian.answer.v1 import (
    answer_delivery_pb2 as delivery_pb2,
)


class R2WorkerScriptTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_worker_owns_one_ready_client_and_both_summary_operations(self) -> None:
        module = _load_script_module("process_summary_jobs.py")
        client = SimpleNamespace(close=AsyncMock())
        expected_result = object()
        captured = {}
        open_client = AsyncMock(return_value=client)

        def process(options):
            captured["options"] = options
            return expected_result

        with patch.object(module, "open_r2_client", new=open_client), patch.object(
            module, "process_summary_jobs", side_effect=process
        ):
            result = await module._run_r2_summary_worker(_summary_args(), model="gpt-5.6-sol")

        self.assertIs(result, expected_result)
        open_client.assert_awaited_once_with(expected_principal="summary-worker")
        client.close.assert_awaited_once()
        generator = captured["options"].generator_factory()
        self.assertEqual(generator.default_operation, delivery_pb2.BOOK_SUMMARIZATION)
        self.assertEqual(generator.model, "gpt-5.6-sol")

    async def test_metadata_worker_maps_tag_and_genre_jobs_to_their_contract_operations(self) -> None:
        module = _load_script_module("process_metadata_jobs.py")
        client = SimpleNamespace(close=AsyncMock())
        expected_result = object()
        captured = {}
        open_client = AsyncMock(return_value=client)

        def process(options):
            captured["options"] = options
            return expected_result

        with patch.object(module, "open_r2_client", new=open_client), patch.object(
            module, "process_metadata_jobs", side_effect=process
        ):
            result = await module._run_r2_metadata_worker(_metadata_args(), model="gpt-5.6-sol")

        self.assertIs(result, expected_result)
        open_client.assert_awaited_once_with(expected_principal="metadata-worker")
        client.close.assert_awaited_once()
        factory = captured["options"].generator_factory
        self.assertEqual(
            factory("tags").default_operation,
            delivery_pb2.TAG_GENERATION,
        )
        self.assertEqual(
            factory("genres").default_operation,
            delivery_pb2.GENRE_GENERATION,
        )


def _load_script_module(name: str):
    path = REPO_ROOT / "scripts" / name
    module_name = f"r2_worker_script_{path.stem}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _summary_args():
    return SimpleNamespace(
        watch=False,
        database_url="sqlite:////data/librarian.db",
        limit=1,
        poll_interval_seconds=10.0,
        max_cycles=None,
        idle_exit_after=None,
        include_chapter_summaries=False,
        chunk_summary_timeout_seconds=None,
        max_parallel_chunk_summaries=None,
        no_enqueue_metadata_jobs=False,
    )


def _metadata_args():
    return SimpleNamespace(
        watch=False,
        database_url="sqlite:////data/librarian.db",
        limit=1,
        poll_interval_seconds=10.0,
        max_cycles=None,
        idle_exit_after=None,
        job_type=None,
        max_tags=12,
        max_secondary_genres=3,
    )


if __name__ == "__main__":
    unittest.main()
