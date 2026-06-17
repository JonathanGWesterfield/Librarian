import json
import sys
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "play"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ingestion"))

from chat import main as chat_main
from librarian import main as librarian_main

try:
    from fastapi.testclient import TestClient
    from librarian_api.main import app
except (ModuleNotFoundError, RuntimeError) as error:
    TestClient = None
    app = None
    API_IMPORT_ERROR = error
else:
    API_IMPORT_ERROR = None


class LocalPipelineCliE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_pipeline_ingests_embeds_searches_and_answers(self) -> None:
        """Verify the local CLI path works from EPUB ingestion to chat answer.
        This is the broad regression net for repo cleanup: it uses real parsing,
        chunking, SQLite storage, embedding rebuild, vector search, and chat
        generation while replacing only the external Ollama process.
        """
        with fake_ollama_transport() as ollama:
            ingest = self._run_librarian_json(
                [
                    "--database-url",
                    self.database_url,
                    "ingest",
                    "--books-dir",
                    str(self.books_dir),
                ]
            )
            embed = self._run_librarian_json(
                [
                    "--database-url",
                    self.database_url,
                    "embed",
                    "--embedding-provider",
                    "ollama",
                    "--embedding-model",
                    "all-minilm",
                    "--ollama-base-url",
                    ollama.base_url,
                    "--reset",
                ]
            )
            search = self._run_librarian_json(
                [
                    "--database-url",
                    self.database_url,
                    "search",
                    "clockwork garden",
                    "--embedding-provider",
                    "ollama",
                    "--embedding-model",
                    "all-minilm",
                    "--ollama-base-url",
                    ollama.base_url,
                    "--limit",
                    "5",
                ]
            )
            chat = self._run_chat_json(
                [
                    "--database-url",
                    self.database_url,
                    "--embedding-provider",
                    "ollama",
                    "--embedding-model",
                    "all-minilm",
                    "--generation-provider",
                    "ollama",
                    "--generation-model",
                    "llama3.2:3b",
                    "--ollama-base-url",
                    ollama.base_url,
                    "--retrieval-limit",
                    "5",
                    "What happened in the clockwork garden?",
                ]
            )

        self.assertEqual(ingest["parsed"], 1)
        self.assertEqual(ingest["total_chunks"], 1)
        self.assertEqual(embed["chunks_seen"], 1)
        self.assertEqual(embed["embeddings_stored"], 1)
        self.assertEqual(search["candidate_count"], 1)
        self.assertIn("The clockwork garden woke at dawn.", search["results"][0]["text"])
        self.assertIn("[S1]", chat["answer"])
        self.assertEqual(chat["sources"][0]["source_id"], "S1")
        self.assertIn("The Clockwork Garden", chat["sources"][0]["title"])

    def _run_librarian_json(self, args: list[str]) -> dict[str, object]:
        return _run_json(librarian_main, [*args, "--json"])

    def _run_chat_json(self, args: list[str]) -> dict[str, object]:
        return _run_json(chat_main, [*args, "--json"])


@unittest.skipIf(
    TestClient is None,
    f"API dependencies are not installed: {API_IMPORT_ERROR}",
)
class LocalPipelineApiE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_api_pipeline_ingests_embeds_searches_and_answers(self) -> None:
        """Verify the API path supports a future desktop shell end to end.
        The test drives public HTTP endpoints in sequence so route wiring,
        request fields, package services, storage, and response shapes all fail
        together if a cleanup breaks the product flow.
        """
        with fake_ollama_transport() as ollama:
            ingest_response = self.client.post(
                "/ingestion/run",
                json={
                    "books_dir": str(self.books_dir),
                    "database_url": self.database_url,
                },
            )
            embed_response = self.client.post(
                "/embeddings/rebuild",
                json={
                    "database_url": self.database_url,
                    "embedding_provider": "ollama",
                    "embedding_model": "all-minilm",
                    "ollama_base_url": ollama.base_url,
                    "reset": True,
                },
            )
            search_response = self.client.post(
                "/search",
                json={
                    "query": "clockwork garden",
                    "database_url": self.database_url,
                    "embedding_provider": "ollama",
                    "embedding_model": "all-minilm",
                    "ollama_base_url": ollama.base_url,
                    "limit": 5,
                },
            )
            chat_response = self.client.post(
                "/chat",
                json={
                    "question": "What happened in the clockwork garden?",
                    "database_url": self.database_url,
                    "embedding_provider": "ollama",
                    "embedding_model": "all-minilm",
                    "generation_provider": "ollama",
                    "generation_model": "llama3.2:3b",
                    "ollama_base_url": ollama.base_url,
                    "retrieval_limit": 5,
                },
            )

        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(embed_response.status_code, 200)
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(chat_response.status_code, 200)
        self.assertEqual(ingest_response.json()["parsed"], 1)
        self.assertEqual(embed_response.json()["embeddings_stored"], 1)
        self.assertEqual(search_response.json()["candidate_count"], 1)
        self.assertIn("[S1]", chat_response.json()["answer"])
        self.assertEqual(chat_response.json()["sources"][0]["source_id"], "S1")


def _run_json(main_func, args: list[str]) -> dict[str, object]:
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main_func(args)
    if exit_code != 0:
        raise AssertionError(f"command failed with {exit_code}: {output.getvalue()}")
    return json.loads(output.getvalue())


@contextmanager
def fake_ollama_transport():
    transport = _FakeOllamaTransport()
    with patch("urllib.request.urlopen", side_effect=transport.urlopen):
        yield transport


class _FakeOllamaTransport:
    base_url = "http://fake-ollama.local"

    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def urlopen(self, http_request, timeout=None):
        payload = json.loads(http_request.data.decode("utf-8"))
        self.requests.append(
            {
                "url": http_request.full_url,
                "payload": payload,
                "timeout": timeout,
            }
        )
        if http_request.full_url == f"{self.base_url}/api/embed":
            inputs = payload.get("input", [])
            return _FakeResponse(
                {
                    "model": payload.get("model"),
                    "embeddings": [_embedding_for_text(str(text)) for text in inputs],
                }
            )

        if http_request.full_url == f"{self.base_url}/api/chat":
            messages = payload.get("messages", [])
            prompt = messages[-1]["content"] if messages else ""
            answer = (
                "The source says the clockwork garden woke at dawn, with its "
                "mechanical life beginning in careful motion. [S1]"
            )
            if "Source chunks" not in prompt:
                answer = "The local library context is insufficient."
            return _FakeResponse(
                {
                    "model": payload.get("model"),
                    "message": {"role": "assistant", "content": answer},
                }
            )

        raise AssertionError(f"unexpected Ollama URL: {http_request.full_url}")


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _embedding_for_text(text: str) -> list[float]:
    normalized = text.casefold()
    if "clockwork" in normalized or "garden" in normalized:
        return [1.0, 0.0, 0.0]
    if "ocean" in normalized or "moonlight" in normalized:
        return [0.0, 1.0, 0.0]
    return [0.5, 0.5, 0.0]


if __name__ == "__main__":
    unittest.main()
