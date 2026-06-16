import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "play"))

from librarian import main


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

    def _run_json(self, args: list[str]) -> object:
        return json.loads(self._run_cli([*args, "--json"]))

    def _run_cli(self, args: list[str]) -> str:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(args)
        self.assertEqual(exit_code, 0)
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
