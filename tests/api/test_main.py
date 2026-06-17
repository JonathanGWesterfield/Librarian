import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ingestion"))

from librarian_chat import ChatResponse, ChatSource
from librarian_storage import (
    BookRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    utc_now,
)

try:
    from fastapi.testclient import TestClient
    from librarian_api.main import app
except (ModuleNotFoundError, RuntimeError) as error:
    TestClient = None
    app = None
    API_IMPORT_ERROR = error
else:
    API_IMPORT_ERROR = None


@unittest.skipIf(
    TestClient is None,
    f"API dependencies are not installed: {API_IMPORT_ERROR}",
)
class IngestionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.books_dir = REPO_ROOT / "tests" / "fixtures" / "epubs"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingestion_endpoints_support_desktop_clients(self) -> None:
        """Verify the API exposes ingestion, summary, and book listing flows.
        A future Electron or Tauri app can use these endpoints instead of
        shelling out to the CLI for common ingestion actions.
        """
        run_response = self.client.post(
            "/ingestion/run",
            json={
                "books_dir": str(self.books_dir),
                "database_url": self.database_url,
                "list_epubs": True,
            },
        )

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["parsed"], 1)

        summary_response = self.client.get(
            "/ingestion/summary",
            params={"database_url": self.database_url},
        )
        books_response = self.client.get(
            "/books",
            params={"database_url": self.database_url},
        )

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(books_response.status_code, 200)
        self.assertEqual(summary_response.json()["total_books"], 1)
        self.assertEqual(books_response.json()[0]["relative_path"], "sample.epub")

    def test_embedding_rebuild_endpoint_supports_noop_rebuilds(self) -> None:
        """Verify desktop clients can trigger embedding maintenance.
        The endpoint should operate on existing chunk rows and return counts
        even when the no-op provider is used for local tests.
        """
        self.client.post(
            "/ingestion/run",
            json={
                "books_dir": str(self.books_dir),
                "database_url": self.database_url,
            },
        )

        response = self.client.post(
            "/embeddings/rebuild",
            json={
                "database_url": self.database_url,
                "embedding_provider": "noop",
                "reset": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chunks_seen"], 1)
        self.assertEqual(response.json()["embeddings_stored"], 0)

    def test_query_embedding_endpoint_supports_provider_selection(self) -> None:
        """Verify clients can create an embedding for a user query.
        The no-op provider keeps the endpoint test local while proving request
        validation and response shape before retrieval uses real vectors.
        """
        response = self.client.post(
            "/embeddings/query",
            json={
                "query": "clockwork gardens",
                "embedding_provider": "noop",
            },
        )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "clockwork gardens")
        self.assertEqual(payload["embedding_provider"], "noop")
        self.assertEqual(payload["dimensions"], 0)
        self.assertEqual(payload["vector"], [])

    def test_search_endpoint_returns_ranked_chunks(self) -> None:
        """Verify desktop clients can run the first retrieval flow through HTTP.
        The test seeds real SQLite rows, then patches only query embedding so
        the endpoint can prove ranking behavior without requiring Ollama.
        """
        self._seed_search_fixture()

        with patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeQueryEmbedder(),
        ):
            response = self.client.post(
                "/search",
                json={
                    "query": "clockwork garden",
                    "database_url": self.database_url,
                    "embedding_provider": "ollama",
                    "embedding_model": "all-minilm",
                    "limit": 2,
                },
            )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "clockwork garden")
        self.assertEqual(payload["embedding_provider"], "ollama")
        self.assertEqual(payload["embedding_model"], "all-minilm")
        self.assertEqual(payload["dimensions"], 2)
        self.assertEqual(payload["candidate_count"], 3)
        self.assertEqual(len(payload["results"]), 2)
        self.assertEqual(payload["results"][0]["chunk_id"], "api-book:0")
        self.assertAlmostEqual(payload["results"][0]["score"], 1.0, places=6)
        self.assertIn("clockwork garden", payload["results"][0]["text"])

    def test_chat_endpoint_returns_answer_with_sources(self) -> None:
        """Verify desktop clients can request grounded answer synthesis.
        The route should expose the chat service response shape while letting
        the package layer handle retrieval and local generation details.
        """
        fake_response = ChatResponse(
            question="How brutal is war?",
            answer="War is presented as terrifying and dehumanizing. [S1]",
            embedding_provider="ollama",
            embedding_model="all-minilm",
            generation_provider="ollama",
            generation_model="llama3.2:3b",
            retrieval_limit=20,
            candidate_count=3,
            sources=[
                ChatSource(
                    source_id="S1",
                    score=0.9,
                    chunk_id="api-book:0",
                    book_id="api-book",
                    relative_path="api-sample.epub",
                    title="API Sample Book",
                    authors=["Test Author"],
                    chunk_index=0,
                    text="The front is terrifying.",
                )
            ],
        )
        with patch("librarian_api.main.answer_question", return_value=fake_response):
            response = self.client.post(
                "/chat",
                json={
                    "question": "How brutal is war?",
                    "database_url": self.database_url,
                    "embedding_provider": "ollama",
                    "embedding_model": "all-minilm",
                    "generation_provider": "ollama",
                    "generation_model": "llama3.2:3b",
                    "retrieval_limit": 20,
                },
            )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["answer"], fake_response.answer)
        self.assertEqual(payload["generation_model"], "llama3.2:3b")
        self.assertEqual(payload["sources"][0]["source_id"], "S1")

    def _seed_search_fixture(self) -> None:
        book = BookRecord(
            id="api-book",
            source_path="/books/api-sample.epub",
            relative_path="api-sample.epub",
            file_hash="api-book",
            size_bytes=100,
            title="API Sample Book",
            authors=["Test Author"],
            publisher="Fixture Press",
            status="ingested",
            ingested_at=utc_now(),
        )
        chunks = [
            ChunkRecord(
                id="api-book:0",
                book_id="api-book",
                chunk_index=0,
                text="The clockwork garden woke at dawn.",
                character_count=35,
                token_estimate=8,
            ),
            ChunkRecord(
                id="api-book:1",
                book_id="api-book",
                chunk_index=1,
                text="A distant ocean rolled under moonlight.",
                character_count=39,
                token_estimate=9,
            ),
            ChunkRecord(
                id="api-book:2",
                book_id="api-book",
                chunk_index=2,
                text="The brass robin counted silver seeds.",
                character_count=38,
                token_estimate=9,
            ),
        ]
        embeddings = [
            EmbeddingRecord(
                id="api-book:0:ollama:all-minilm",
                chunk_id="api-book:0",
                provider="ollama",
                model="all-minilm",
                vector=[1.0, 0.0],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="api-book:1:ollama:all-minilm",
                chunk_id="api-book:1",
                provider="ollama",
                model="all-minilm",
                vector=[0.0, 1.0],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="api-book:2:ollama:all-minilm",
                chunk_id="api-book:2",
                provider="ollama",
                model="all-minilm",
                vector=[0.7, 0.7],
                dimensions=2,
            ),
        ]
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, chunks)
            store.save_chunk_embeddings(embeddings)


class _FakeQueryEmbedder:
    provider = "ollama"
    model = "all-minilm"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]
