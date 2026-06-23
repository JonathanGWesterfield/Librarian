import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_chat.chat import ChatResponse, ChatSource
from librarian_metadata.genres import BookGenreGenerationResult, GeneratedBookGenre
from librarian_storage.storage import (
    BookGenreRecord,
    BookRecord,
    BookSummaryRecord,
    BookTagRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    SummaryJobRecord,
    utc_now,
)
from librarian_summarization.summarize import BookSummary

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
                "enqueue_summaries": True,
                "summary_generation_provider": "codex",
                "summary_generation_model": "codex",
            },
        )

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["parsed"], 1)
        self.assertEqual(run_response.json()["summary_jobs_enqueued"], 1)

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
        with SQLiteIngestionStore(self.database_path) as store:
            self.assertEqual(len(store.list_summary_jobs(status="pending")), 1)

    def test_ingestion_status_endpoint_returns_stage_progress(self) -> None:
        """Verify clients can show ingestion progress across pipeline stages.
        The response should tell a UI how much chunking, summarizing, and
        tagging work is complete, pending, running, or failed.
        """
        self._seed_ingestion_status_fixture()

        response = self.client.get(
            "/ingestion/status",
            params={"database_url": self.database_url},
        )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["database_url"], self.database_url)
        self.assertEqual(payload["total_books"], 2)
        self.assertEqual(payload["chunking"]["status"], "complete")
        self.assertEqual(payload["chunking"]["completed_books"], 2)
        self.assertEqual(payload["chunking"]["details"]["total_chunks"], 2)
        self.assertEqual(payload["summarizing"]["status"], "running")
        self.assertEqual(payload["summarizing"]["completed_books"], 1)
        self.assertEqual(payload["summarizing"]["pending_books"], 0)
        self.assertEqual(payload["summarizing"]["running_books"], 1)
        self.assertEqual(payload["summarizing"]["details"]["summary_jobs_pending"], 0)
        self.assertEqual(payload["summarizing"]["details"]["summary_jobs_running"], 1)
        self.assertEqual(
            payload["summarizing"]["active_jobs"][0]["title"],
            "API Sample Two",
        )
        self.assertEqual(payload["summarizing"]["active_jobs"][0]["stage"], "chapter")
        self.assertEqual(payload["summarizing"]["active_jobs"][0]["current"], 1)
        self.assertEqual(payload["summarizing"]["active_jobs"][0]["total"], 2)
        self.assertEqual(payload["tagging"]["status"], "in_progress")
        self.assertEqual(payload["tagging"]["completed_books"], 1)
        self.assertEqual(payload["tagging"]["pending_books"], 1)
        self.assertEqual(payload["tagging"]["details"]["total_tags"], 1)
        self.assertEqual(payload["tagging"]["details"]["total_genres"], 1)

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
                    "author": "Test Author",
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
        self.assertEqual(payload["filters"], {"author": "Test Author"})
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
            filters={"book_title": "All Quiet"},
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
                    "book_title": "All Quiet",
                },
            )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["answer"], fake_response.answer)
        self.assertEqual(payload["generation_model"], "llama3.2:3b")
        self.assertEqual(payload["filters"], {"book_title": "All Quiet"})
        self.assertEqual(payload["sources"][0]["source_id"], "S1")

    def test_book_summary_endpoint_returns_on_demand_summary(self) -> None:
        """Verify desktop clients can request a first-class book summary.
        The endpoint should stay separate from chat routing and expose summary
        cache/rebuild metadata for local experimentation.
        """
        fake_summary = BookSummary(
            book_id="forward-foundation",
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            provider="codex",
            model="codex",
            detail="medium",
            summary="Hari Seldon's work on psychohistory moves toward Foundation.",
            source_hash="hash",
            chapter_summary_count=1,
            cached_chapter_summaries=0,
            generated_chapter_summaries=1,
            deleted_summaries=0,
            chapter_summaries=[],
        )

        with patch("librarian_api.main.summarize_book", return_value=fake_summary):
            response = self.client.post(
                "/books/forward-foundation/summary",
                json={
                    "database_url": self.database_url,
                    "generation_provider": "codex",
                    "generation_model": "codex",
                    "detail": "medium",
                    "reset": True,
                },
            )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["title"], "Forward the Foundation")
        self.assertEqual(payload["provider"], "codex")
        self.assertEqual(payload["chapter_summary_count"], 1)

    def test_book_genres_endpoint_returns_generated_genres(self) -> None:
        """Verify desktop clients can trigger genre generation over HTTP.
        The route should expose the metadata service response while keeping
        prompt execution inside the package layer.
        """
        fake_result = BookGenreGenerationResult(
            book_id="forward-foundation",
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            source_summary_provider="codex",
            source_summary_model="codex",
            source_summary_detail="medium",
            generation_provider="codex",
            generation_model="codex",
            deleted_genres=0,
            generated_genres=2,
            cached_genres=0,
            genres=[
                GeneratedBookGenre(
                    genre="Science Fiction",
                    genre_role="primary",
                    confidence=0.96,
                    rationale="Foundation is science fiction.",
                    cached=False,
                ),
                GeneratedBookGenre(
                    genre="Political Fiction",
                    genre_role="secondary",
                    confidence=0.74,
                    rationale="Imperial politics shape the story.",
                    cached=False,
                ),
            ],
        )

        with patch("librarian_api.main.generate_book_genres", return_value=fake_result):
            response = self.client.post(
                "/books/forward-foundation/genres",
                json={
                    "database_url": self.database_url,
                    "source_summary_provider": "codex",
                    "source_summary_model": "codex",
                    "generation_provider": "codex",
                    "generation_model": "codex",
                    "reset": True,
                },
            )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["title"], "Forward the Foundation")
        self.assertEqual(payload["generated_genres"], 2)
        self.assertEqual(payload["genres"][0]["genre"], "Science Fiction")
        self.assertEqual(payload["genres"][0]["genre_role"], "primary")

    def test_book_genres_endpoint_lists_and_deletes_stored_genres(self) -> None:
        """Verify clients can inspect and clean up stored genre metadata.
        The GET/DELETE endpoints should use the same storage-backed filters as
        the CLI so a future desktop app can manage genre records directly.
        """
        self._seed_genre_fixture()

        list_response = self.client.get(
            "/books/api-book/genres",
            params={
                "database_url": self.database_url,
                "genre_role": "primary",
                "provider": "codex",
                "model": "codex",
            },
        )
        delete_response = self.client.delete(
            "/books/api-book/genres",
            params={
                "database_url": self.database_url,
                "source": "llm",
            },
        )
        remaining_response = self.client.get(
            "/books/api-book/genres",
            params={"database_url": self.database_url},
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()[0]["genre"], "Science Fiction")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json(), {"deleted_genres": 2})
        self.assertEqual(remaining_response.status_code, 200)
        self.assertEqual(remaining_response.json(), [])

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

    def _seed_genre_fixture(self) -> None:
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
        genres = [
            BookGenreRecord(
                id="api-book:genre:primary",
                book_id="api-book",
                genre="Science Fiction",
                genre_role="primary",
                source="llm",
                confidence=0.96,
                provider="codex",
                model="codex",
                rationale="Speculative setting.",
            ),
            BookGenreRecord(
                id="api-book:genre:secondary",
                book_id="api-book",
                genre="Political Fiction",
                genre_role="secondary",
                source="llm",
                confidence=0.74,
                provider="codex",
                model="codex",
                rationale="Politics matter.",
            ),
        ]
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_book_genres(genres)

    def _seed_ingestion_status_fixture(self) -> None:
        first_book = BookRecord(
            id="api-book-1",
            source_path="/books/api-sample-1.epub",
            relative_path="api-sample-1.epub",
            file_hash="api-book-1",
            size_bytes=100,
            title="API Sample One",
            authors=["Test Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        second_book = BookRecord(
            id="api-book-2",
            source_path="/books/api-sample-2.epub",
            relative_path="api-sample-2.epub",
            file_hash="api-book-2",
            size_bytes=100,
            title="API Sample Two",
            authors=["Test Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        first_chunk = ChunkRecord(
            id="api-book-1:0",
            book_id="api-book-1",
            chunk_index=0,
            text="First book chunk.",
            character_count=17,
            token_estimate=4,
        )
        second_chunk = ChunkRecord(
            id="api-book-2:0",
            book_id="api-book-2",
            chunk_index=0,
            text="Second book chunk.",
            character_count=18,
            token_estimate=4,
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(first_book, [first_chunk])
            store.save_book_with_chunks(second_book, [second_chunk])
            store.save_book_summary(
                BookSummaryRecord(
                    id="api-book-1:summary",
                    book_id="api-book-1",
                    provider="codex",
                    model="codex",
                    detail="medium",
                    source_hash="hash",
                    summary="A finished summary.",
                    chapter_summary_count=1,
                )
            )
            store.save_summary_job(
                SummaryJobRecord(
                    id="api-book-2:summary-job",
                    book_id="api-book-2",
                    provider="codex",
                    model="codex",
                    detail="medium",
                )
            )
            store.claim_summary_job("api-book-2:summary-job", attempts=1)
            store.update_summary_job_progress(
                "api-book-2:summary-job",
                stage="chapter",
                current_step=1,
                total_steps=2,
                message="Generating summary for Chunks 0-0.",
            )
            store.save_book_tags(
                [
                    BookTagRecord(
                        id="api-book-1:tag:psychohistory",
                        book_id="api-book-1",
                        tag="psychohistory",
                        tag_type="topic",
                        source="llm",
                        provider="codex",
                        model="codex",
                    )
                ]
            )
            store.save_book_genres(
                [
                    BookGenreRecord(
                        id="api-book-1:genre:primary",
                        book_id="api-book-1",
                        genre="Science Fiction",
                        genre_role="primary",
                        source="llm",
                        provider="codex",
                        model="codex",
                    )
                ]
            )


class _FakeQueryEmbedder:
    provider = "ollama"
    model = "all-minilm"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]
