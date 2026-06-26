import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_search.opensearch import (  # noqa: E402
    OpenSearchIndexOptions,
    index_chunks,
)
from librarian_storage.storage import (  # noqa: E402
    BookGenreRecord,
    BookRecord,
    BookTagRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    utc_now,
)


class OpenSearchIndexingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_book()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_index_chunks_pushes_embeddings_and_metadata_to_opensearch(self) -> None:
        """Verify SQLite chunks are copied into a rebuildable OpenSearch index.
        OpenSearch should receive text, vector, book metadata, and generated
        tags/genres so hybrid retrieval can filter and rank without scanning
        SQLite embeddings.
        """
        with fake_opensearch_transport() as transport:
            result = index_chunks(
                OpenSearchIndexOptions(
                    database_url=self.database_url,
                    opensearch_url="http://fake-opensearch.local",
                    index_name="librarian-test",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    reset=True,
                    batch_size=1,
                )
            )

        self.assertEqual(result.documents_seen, 1)
        self.assertEqual(result.documents_indexed, 1)
        self.assertEqual(result.dimensions, 2)
        self.assertEqual(transport.requests[0]["method"], "DELETE")
        self.assertEqual(transport.requests[1]["method"], "PUT")
        vector_mapping = transport.requests[1]["payload"]["mappings"]["properties"]["vector"]
        self.assertEqual(vector_mapping["dimension"], 2)
        bulk_lines = transport.requests[2]["raw_body"].strip().splitlines()
        document = json.loads(bulk_lines[1])
        self.assertEqual(document["chunk_id"], "book-1:0")
        self.assertEqual(document["vector"], [1.0, 0.0])
        self.assertEqual(document["tags"], ["clockwork garden"])
        self.assertEqual(document["genres"], ["Science Fiction"])

    def _seed_book(self) -> None:
        book = BookRecord(
            id="book-1",
            source_path="/books/book.epub",
            relative_path="book.epub",
            file_hash="book-1",
            size_bytes=100,
            title="The Clockwork Garden",
            authors=["Test Author"],
            publisher="Fixture Press",
            status="ingested",
            ingested_at=utc_now(),
        )
        chunk = ChunkRecord(
            id="book-1:0",
            book_id="book-1",
            chunk_index=0,
            text="The clockwork garden woke at dawn.",
            character_count=36,
            token_estimate=7,
        )
        embedding = EmbeddingRecord(
            id="book-1:0:ollama:all-minilm",
            chunk_id="book-1:0",
            provider="ollama",
            model="all-minilm",
            vector=[1.0, 0.0],
            dimensions=2,
        )
        tag = BookTagRecord(
            id="book-1:tag",
            book_id="book-1",
            tag="clockwork garden",
            tag_type="topic",
            source="llm",
            confidence=0.9,
            provider="ollama",
            model="llama3.2:3b",
            rationale="Fixture tag.",
        )
        genre = BookGenreRecord(
            id="book-1:genre",
            book_id="book-1",
            genre="Science Fiction",
            genre_role="primary",
            source="llm",
            confidence=0.9,
            provider="ollama",
            model="llama3.2:3b",
            rationale="Fixture genre.",
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [chunk])
            store.save_chunk_embeddings([embedding])
            store.save_book_tags([tag])
            store.save_book_genres([genre])


@contextmanager
def fake_opensearch_transport():
    transport = _FakeOpenSearchTransport()
    with patch("urllib.request.urlopen", side_effect=transport.urlopen):
        yield transport


class _FakeOpenSearchTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def urlopen(self, http_request, timeout=None):
        raw_body = http_request.data.decode("utf-8") if http_request.data else ""
        payload = (
            json.loads(raw_body)
            if raw_body and not http_request.full_url.endswith("/_bulk")
            else None
        )
        self.requests.append(
            {
                "method": http_request.get_method(),
                "url": http_request.full_url,
                "payload": payload,
                "raw_body": raw_body,
                "timeout": timeout,
            }
        )
        if http_request.get_method() == "DELETE":
            return _FakeResponse({})
        if http_request.get_method() == "PUT":
            return _FakeResponse({"acknowledged": True})
        if http_request.full_url.endswith("/_bulk"):
            return _FakeResponse({"errors": False, "items": []})
        raise AssertionError(f"unexpected OpenSearch request: {http_request.full_url}")


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
