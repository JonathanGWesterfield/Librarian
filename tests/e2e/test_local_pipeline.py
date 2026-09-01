import json
import sys
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import error
from unittest.mock import patch
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "play"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from chat import main as chat_main
from librarian import main as librarian_main
from librarian_ingestion.scan import scan_epub_files
from librarian_storage.storage import (
    BookRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    create_ingestion_store,
    utc_now,
)
from process_metadata_jobs import main as process_metadata_jobs_main
from process_summary_jobs import main as process_summary_jobs_main
from tests.ingestion.fixtures import SAMPLE_EPUB

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
                    "--answer-capability",
                    "quality",
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
        self.assertEqual(chat["retrieval_backend"], "sqlite")
        self.assertEqual(chat["sources"][0]["source_id"], "S1")
        self.assertIn("The Clockwork Garden", chat["sources"][0]["title"])

    def test_cli_workers_summarize_tag_and_report_progress(self) -> None:
        """Verify queued background work survives the local CLI workflow.
        The ingestion call should enqueue durable summary work, the summary
        worker should produce summaries and enqueue metadata jobs, the metadata
        worker should store tags/genres, and the status API should expose
        progress plus timing fields for the UI.
        """
        with fake_ollama_transport() as ollama:
            ingest = self._run_librarian_json(
                [
                    "--database-url",
                    self.database_url,
                    "ingest",
                    "--books-dir",
                    str(self.books_dir),
                    "--enqueue-summaries",
                    "--summary-generation-provider",
                    "ollama",
                    "--summary-generation-model",
                    "llama3.2:3b",
                ]
            )
            summary = _run_json(
                process_summary_jobs_main,
                [
                    "--database-url",
                    self.database_url,
                    "--limit",
                    "1",
                    "--max-parallel-chunk-summaries",
                    "2",
                    "--json",
                ],
            )
            metadata = _run_json(
                process_metadata_jobs_main,
                [
                    "--database-url",
                    self.database_url,
                    "--limit",
                    "2",
                    "--max-tags",
                    "3",
                    "--max-secondary-genres",
                    "2",
                    "--json",
                ],
            )

        self.assertEqual(ingest["parsed"], 1)
        self.assertEqual(ingest["summary_jobs_enqueued"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertIn("2 metadata jobs queued", summary["jobs"][0]["message"])
        self.assertEqual(metadata["completed"], 2)

        store = create_ingestion_store(self.database_url)
        store.initialize()
        try:
            book = store.list_books()[0]
            book_summary = store.get_book_summary(
                book_id=book.id,
                provider="ollama",
                model="llama3.2:3b",
                detail="medium",
            )
            completed_summary_jobs = store.list_summary_jobs(
                status="completed",
                book_id=book.id,
            )
            completed_metadata_jobs = store.list_metadata_jobs(
                status="completed",
                book_id=book.id,
            )
            tags = store.list_book_tags(book_id=book.id)
            genres = store.list_book_genres(book_id=book.id)
            pipeline_status = store.get_ingestion_status()
        finally:
            store.close()

        self.assertIsNotNone(book_summary)
        self.assertEqual(len(completed_summary_jobs), 1)
        self.assertEqual(len(completed_metadata_jobs), 2)
        self.assertGreaterEqual(completed_summary_jobs[0].duration_seconds or 0, 0)
        self.assertTrue({tag.tag for tag in tags} >= {"clockwork garden", "dawn"})
        self.assertEqual(
            [(genre.genre, genre.genre_role) for genre in genres],
            [("Science Fiction", "primary"), ("Fantasy", "secondary")],
        )
        self.assertEqual(pipeline_status.summarizing.status, "complete")
        self.assertEqual(pipeline_status.tagging.status, "complete")
        self.assertIn(
            "total_summary_duration_seconds",
            pipeline_status.summarizing.details,
        )
        self.assertIn(
            "total_metadata_duration_seconds",
            pipeline_status.tagging.details,
        )

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
                    "answer_capability": "quality",
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
        self.assertEqual(chat_response.json()["retrieval_backend"], "sqlite")
        self.assertEqual(chat_response.json()["sources"][0]["source_id"], "S1")

    def test_default_lightweight_lookup_is_repeatably_source_faithful(self) -> None:
        """Default Docker Ollama lookups keep adjacent source facts separate.

        This exercises ingestion, embeddings, retrieval, and the public chat
        endpoint with the configured ``qwen2.5:1.5b`` lightweight default.
        The fake transport deliberately gives a wrong combined-subject answer
        if chat generation is reached; a direct lookup must instead return the
        matching local sentence on every request.
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
            responses = [
                self.client.post(
                    "/chat",
                    json={
                        "question": "What woke at dawn in The Clockwork Garden?",
                        "database_url": self.database_url,
                        "embedding_provider": "ollama",
                        "embedding_model": "all-minilm",
                        "ollama_base_url": ollama.base_url,
                        "book_title": "The Clockwork Garden",
                    },
                )
                for _ in range(3)
            ]

        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(embed_response.status_code, 200)
        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(
            [response.json()["answer"] for response in responses],
            ["The clockwork garden woke at dawn. [S1]"] * 3,
        )
        self.assertTrue(
            all(response.json()["answer_capability"] == "lightweight" for response in responses)
        )
        self.assertFalse(
            any(request["url"].endswith("/api/chat") for request in ollama.requests)
        )

    def test_api_reprocesses_unchanged_epubs_and_restores_body_search(self) -> None:
        """A deliberate API reprocess repairs legacy content roles and embeddings.

        This models a library ingested before the exact filename classifier:
        the unchanged stock-market EPUB already has a front-matter chunk, so
        default search hides it. A normal update must still hash-skip the book;
        the explicit remediation request reparses, re-embeds, and exposes it.
        """
        with TemporaryDirectory() as temp_dir:
            books_dir = Path(temp_dir) / "books"
            books_dir.mkdir()
            _write_stock_market_epub(books_dir / "stock-market.epub")
            discovered = scan_epub_files(books_dir)[0]
            self._seed_legacy_stock_market_record(discovered)

            with fake_ollama_transport() as ollama:
                before = self.client.post(
                    "/search",
                    json={
                        "query": "stock market",
                        "database_url": self.database_url,
                        "embedding_provider": "ollama",
                        "embedding_model": "all-minilm",
                        "ollama_base_url": ollama.base_url,
                    },
                )
                ordinary_update = self.client.post(
                    "/ingestion/run",
                    json={
                        "books_dir": str(books_dir),
                        "database_url": self.database_url,
                    },
                )
                reprocess = self.client.post(
                    "/ingestion/run",
                    json={
                        "books_dir": str(books_dir),
                        "database_url": self.database_url,
                        "reprocess_unchanged": True,
                        "embed_chunks": True,
                        "embedding_provider": "ollama",
                        "embedding_model": "all-minilm",
                        "ollama_base_url": ollama.base_url,
                    },
                )
                after = self.client.post(
                    "/search",
                    json={
                        "query": "stock market",
                        "database_url": self.database_url,
                        "embedding_provider": "ollama",
                        "embedding_model": "all-minilm",
                        "ollama_base_url": ollama.base_url,
                    },
                )

        with SQLiteIngestionStore(self.database_path) as store:
            repaired_chunks = [
                chunk
                for chunk in store.list_chunks()
                if "The stock market opened after the bell." in chunk.text
            ]
            repaired_embeddings = store.list_embeddings(
                provider="ollama",
                model="all-minilm",
            )

        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["candidate_count"], 0)
        self.assertEqual(ordinary_update.status_code, 200)
        self.assertEqual(ordinary_update.json()["parsed"], 0)
        self.assertEqual(ordinary_update.json()["skipped_unchanged"], 1)
        self.assertEqual(reprocess.status_code, 200)
        self.assertEqual(reprocess.json()["parsed"], 1)
        self.assertGreater(reprocess.json()["stored_embeddings"], 0)
        self.assertEqual([chunk.content_type for chunk in repaired_chunks], ["body"])
        self.assertGreater(len(repaired_embeddings), 0)
        self.assertEqual(after.status_code, 200)
        self.assertTrue(
            any(
                "The stock market opened after the bell." in result["text"]
                for result in after.json()["results"]
            )
        )

    def test_api_status_reports_background_summary_and_metadata_progress(self) -> None:
        """Verify the status endpoint reflects worker-completed background stages.
        This protects the future desktop progress view by checking the HTTP
        response after real summary and metadata workers update SQLite.
        """
        with fake_ollama_transport() as ollama:
            ingest_response = self.client.post(
                "/ingestion/run",
                json={
                    "books_dir": str(self.books_dir),
                    "database_url": self.database_url,
                    "enqueue_summaries": True,
                    "summary_generation_provider": "ollama",
                    "summary_generation_model": "llama3.2:3b",
                },
            )
            summary = _run_json(
                process_summary_jobs_main,
                [
                    "--database-url",
                    self.database_url,
                    "--limit",
                    "1",
                    "--json",
                ],
            )
            metadata = _run_json(
                process_metadata_jobs_main,
                [
                    "--database-url",
                    self.database_url,
                    "--limit",
                    "2",
                    "--json",
                ],
            )
            status_response = self.client.get(
                "/ingestion/status",
                params={"database_url": self.database_url},
            )

        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(metadata["completed"], 2)
        payload = status_response.json()
        self.assertEqual(payload["summarizing"]["status"], "complete")
        self.assertEqual(payload["tagging"]["status"], "complete")
        self.assertEqual(payload["summarizing"]["completed_books"], 1)
        self.assertEqual(payload["tagging"]["completed_books"], 1)
        self.assertIn(
            "total_summary_duration_seconds",
            payload["summarizing"]["details"],
        )
        self.assertIn(
            "total_metadata_duration_seconds",
            payload["tagging"]["details"],
        )

    def _seed_legacy_stock_market_record(self, discovered) -> None:
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(
                BookRecord(
                    id=discovered.sha256,
                    source_path=str(discovered.path),
                    relative_path=discovered.relative_path,
                    file_hash=discovered.sha256,
                    size_bytes=discovered.size_bytes,
                    title="The Clockwork Garden",
                    authors=["Test Author"],
                    publisher="Fixture Press",
                    status="ingested",
                    ingested_at=utc_now(),
                ),
                [
                    ChunkRecord(
                        id=f"{discovered.sha256}:0",
                        book_id=discovered.sha256,
                        chunk_index=0,
                        text="The stock market opened after the bell.",
                        character_count=39,
                        token_estimate=9,
                        content_type="front_matter",
                    )
                ],
            )
            store.save_chunk_embeddings(
                [
                    EmbeddingRecord(
                        id=f"{discovered.sha256}:0:ollama:all-minilm",
                        chunk_id=f"{discovered.sha256}:0",
                        provider="ollama",
                        model="all-minilm",
                        vector=[0.5, 0.5, 0.0],
                        dimensions=3,
                    )
                ]
            )


def _run_json(main_func, args: list[str]) -> dict[str, object]:
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main_func(args)
    if exit_code != 0:
        raise AssertionError(f"command failed with {exit_code}: {output.getvalue()}")
    return json.loads(output.getvalue())


def _write_stock_market_epub(destination: Path) -> None:
    """Create a valid EPUB whose body chapter name contains the letters ``toc``."""
    manifest_item = (
        '    <item id="stock-market" href="stock-market.xhtml" '
        'media-type="application/xhtml+xml"/>\n'
    )
    spine_item = '    <itemref idref="stock-market"/>\n'
    chapter = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE html>
<html xmlns=\"http://www.w3.org/1999/xhtml\"><body>
  <h1>Stock Market</h1>
  <p>The stock market opened after the bell.</p>
</body></html>
"""
    with ZipFile(SAMPLE_EPUB) as source, ZipFile(destination, "w") as target:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if entry.filename == "OEBPS/content.opf":
                content = content.replace(
                    b"  </manifest>",
                    manifest_item.encode() + b"  </manifest>",
                ).replace(
                    b"  </spine>",
                    spine_item.encode() + b"  </spine>",
                )
            target.writestr(entry, content)
        target.writestr("OEBPS/stock-market.xhtml", chapter.encode())


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
        if http_request.full_url.startswith("http://opensearch:9200/"):
            # This SQLite-only pipeline deliberately has no OpenSearch service.
            # The regular transport failure mirrors an unavailable projection so
            # chat can exercise its configured ``auto`` fallback.
            raise error.URLError("OpenSearch is unavailable in this fixture")
        payload = json.loads(http_request.data.decode("utf-8"))
        self.requests.append(
            {
                "url": http_request.full_url,
                "payload": payload,
                "timeout": timeout,
            }
        )
        if http_request.full_url.endswith("/api/embed"):
            inputs = payload.get("input", [])
            return _FakeResponse(
                {
                    "model": payload.get("model"),
                    "embeddings": [_embedding_for_text(str(text)) for text in inputs],
                }
            )

        if http_request.full_url.endswith("/api/chat"):
            messages = payload.get("messages", [])
            prompt = "\n\n".join(
                str(message.get("content", "")) for message in messages
            )
            answer = self._chat_content(prompt)
            return _FakeResponse(
                {
                    "model": payload.get("model"),
                    "message": {"role": "assistant", "content": answer},
                }
            )

        raise AssertionError(f"unexpected Ollama URL: {http_request.full_url}")

    def _chat_content(self, prompt: str) -> str:
        if "What woke at dawn in The Clockwork Garden?" in prompt:
            return "A brass robin woke at dawn and counted three silver seeds. [S1]"
        if '"tags"' in prompt:
            return json.dumps(
                {
                    "tags": [
                        {
                            "tag": "clockwork garden",
                            "confidence": 0.98,
                            "rationale": "The summary centers on a mechanical garden.",
                        },
                        {
                            "tag": "dawn",
                            "confidence": 0.81,
                            "rationale": "The key scene happens at dawn.",
                        },
                    ]
                }
            )
        if '"primary_genre"' in prompt:
            return json.dumps(
                {
                    "primary_genre": {
                        "genre": "Science Fiction",
                        "confidence": 0.91,
                        "rationale": "The story foregrounds mechanical life.",
                    },
                    "secondary_genres": [
                        {
                            "genre": "Fantasy",
                            "confidence": 0.72,
                            "rationale": "The setting has a fable-like garden.",
                        }
                    ],
                }
            )
        if "Book summary:" in prompt or "Book:" in prompt:
            return (
                "The Clockwork Garden is about a mechanical garden waking at "
                "dawn and revealing careful artificial life."
            )
        if "Source chunks" in prompt:
            return (
                "The source says the clockwork garden woke at dawn, with its "
                "mechanical life beginning in careful motion. [S1]"
            )
        return "The local library context is insufficient."


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
