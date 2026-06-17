import json
import os
import sys
import unittest
from contextlib import contextmanager
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "play"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ingestion"))

from librarian import main
from librarian_storage import EmbeddingRecord, create_ingestion_store


class LibrarianCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_supports_stepwise_ingest_state_chunk_and_embedding_views(self) -> None:
        """Verify the playground CLI exposes tangible pipeline checkpoints.
        The user can ingest EPUBs, inspect database counts, preview chunks, run
        embedding generation, and inspect embedding rows without direct SQL.
        """
        self._run_cli(
            [
                "--database-url",
                self.database_url,
                "ingest",
                "--books-dir",
                str(self.books_dir),
                "--json",
            ]
        )
        state = self._run_json(["--database-url", self.database_url, "state"])
        chunks = self._run_json(["--database-url", self.database_url, "chunks"])
        embed = self._run_json(
            [
                "--database-url",
                self.database_url,
                "embed",
                "--embedding-provider",
                "noop",
                "--reset",
            ]
        )
        embeddings = self._run_json(
            ["--database-url", self.database_url, "embeddings"]
        )

        self.assertEqual(state["total_books"], 1)
        self.assertEqual(state["total_chunks"], 1)
        self.assertIn("The clockwork garden woke at dawn.", chunks[0]["text"])
        self.assertEqual(embed["chunks_seen"], 1)
        self.assertEqual(embed["embeddings_stored"], 0)
        self.assertEqual(embeddings, [])

    def test_cli_search_ranks_stored_chunks(self) -> None:
        """Verify the playground can search the same DB state it helps inspect.
        This keeps the local trial flow honest: after books, chunks, and
        embeddings exist, a user can run one command to see ranked snippets.
        """
        self._run_cli(
            [
                "--database-url",
                self.database_url,
                "ingest",
                "--books-dir",
                str(self.books_dir),
                "--json",
            ]
        )
        self._seed_embedding()

        with patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeQueryEmbedder(),
        ):
            search = self._run_json(
                [
                    "--database-url",
                    self.database_url,
                    "search",
                    "clockwork garden",
                    "--embedding-provider",
                    "ollama",
                    "--embedding-model",
                    "all-minilm",
                ]
            )

        self.assertEqual(search["candidate_count"], 1)
        self.assertEqual(len(search["results"]), 1)
        self.assertAlmostEqual(search["results"][0]["score"], 1.0, places=6)
        self.assertIn("The clockwork garden woke at dawn.", search["results"][0]["text"])

    def test_cli_resolves_books_dir_relative_to_repo_root_from_play_dir(self) -> None:
        """Verify playground commands remain usable from inside scripts/play.
        Developers often run `python3 librarian.py` from that folder, so a
        repo-relative books path should still resolve to the project root.
        """
        with _pushd(REPO_ROOT / "scripts" / "play"):
            result = self._run_json(
                [
                    "--database-url",
                    self.database_url,
                    "ingest",
                    "--books-dir",
                    "tests/fixtures/epubs",
                ]
            )

        self.assertEqual(result["parsed"], 1)
        self.assertEqual(result["total_chunks"], 1)

    def _seed_embedding(self) -> None:
        store = create_ingestion_store(self.database_url)
        store.initialize()
        try:
            chunk = store.list_chunks(limit=1, offset=0)[0]
            store.save_chunk_embeddings(
                [
                    EmbeddingRecord(
                        id=f"{chunk.id}:ollama:all-minilm",
                        chunk_id=chunk.id,
                        provider="ollama",
                        model="all-minilm",
                        vector=[1.0, 0.0],
                        dimensions=2,
                    )
                ]
            )
        finally:
            store.close()

    def _run_json(self, args: list[str]) -> object:
        return json.loads(self._run_cli([*args, "--json"]))

    def _run_cli(self, args: list[str]) -> str:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(args)
        self.assertEqual(exit_code, 0)
        return output.getvalue()


class _FakeQueryEmbedder:
    provider = "ollama"
    model = "all-minilm"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]


@contextmanager
def _pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
