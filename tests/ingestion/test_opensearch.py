import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
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
        self.assertEqual(
            vector_mapping,
            {
                "type": "knn_vector",
                "dimension": 2,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                },
            },
        )
        bulk_lines = transport.requests[2]["raw_body"].strip().splitlines()
        document = json.loads(bulk_lines[1])
        self.assertEqual(document["chunk_id"], "book-1:0")
        self.assertEqual(document["content_type"], "body")
        self.assertEqual(document["vector"], [1.0, 0.0])
        self.assertEqual(document["tags"], ["clockwork garden"])
        self.assertEqual(document["genres"], ["Science Fiction"])
        self.assertEqual(
            transport.requests[1]["payload"]["mappings"]["properties"]["content_type"],
            {"type": "keyword"},
        )
        self.assertEqual(transport.requests[3]["method"], "POST")
        self.assertEqual(
            transport.requests[3]["url"],
            "http://fake-opensearch.local/librarian-test/_refresh",
        )

    def test_incremental_indexing_pages_records_and_skips_existing_chunks(self) -> None:
        """Verify ordinary indexing only sends missing chunks in bounded pages."""
        self._seed_book(book_id="book-2", relative_path="other.epub")

        with fake_opensearch_transport(existing_chunk_ids={"book-1:0"}) as transport:
            result = index_chunks(
                OpenSearchIndexOptions(
                    database_url=self.database_url,
                    opensearch_url="http://fake-opensearch.local",
                    index_name="librarian-test",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    batch_size=1,
                )
            )

        self.assertEqual(result.documents_seen, 2)
        self.assertEqual(result.documents_indexed, 1)
        mget_requests = [
            entry for entry in transport.requests if entry["url"].endswith("/_mget")
        ]
        self.assertEqual(len(mget_requests), 2)
        self.assertTrue(all(len(entry["payload"]["docs"]) == 1 for entry in mget_requests))
        self.assertTrue(
            all(entry["payload"]["docs"][0]["_source"] is False for entry in mget_requests)
        )
        bulk_requests = [
            entry for entry in transport.requests if entry["url"].endswith("/_bulk")
        ]
        self.assertEqual(len(bulk_requests), 1)
        bulk_lines = bulk_requests[0]["raw_body"].strip().splitlines()
        self.assertEqual(json.loads(bulk_lines[0])["index"]["_id"], "book-2:0")

    def _seed_book(self, *, book_id: str = "book-1", relative_path: str = "book.epub") -> None:
        book = BookRecord(
            id=book_id,
            source_path="/books/book.epub",
            relative_path=relative_path,
            file_hash=book_id,
            size_bytes=100,
            title="The Clockwork Garden",
            authors=["Test Author"],
            publisher="Fixture Press",
            status="ingested",
            ingested_at=utc_now(),
        )
        chunk = ChunkRecord(
            id=f"{book_id}:0",
            book_id=book_id,
            chunk_index=0,
            text="The clockwork garden woke at dawn.",
            character_count=36,
            token_estimate=7,
        )
        embedding = EmbeddingRecord(
            id=f"{book_id}:0:ollama:all-minilm",
            chunk_id=f"{book_id}:0",
            provider="ollama",
            model="all-minilm",
            vector=[1.0, 0.0],
            dimensions=2,
        )
        tag = BookTagRecord(
            id=f"{book_id}:tag",
            book_id=book_id,
            tag="clockwork garden",
            tag_type="topic",
            source="llm",
            confidence=0.9,
            provider="ollama",
            model="llama3.2:3b",
            rationale="Fixture tag.",
        )
        genre = BookGenreRecord(
            id=f"{book_id}:genre",
            book_id=book_id,
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
def fake_opensearch_transport(existing_chunk_ids: Optional[set[str]] = None):
    transport = _FakeOpenSearchTransport(existing_chunk_ids=existing_chunk_ids)
    with patch("urllib.request.urlopen", side_effect=transport.urlopen):
        yield transport


class _FakeOpenSearchTransport:
    def __init__(self, *, existing_chunk_ids: Optional[set[str]] = None) -> None:
        self.requests: list[dict[str, object]] = []
        self.existing_chunk_ids = existing_chunk_ids or set()

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
        if http_request.full_url.endswith("/_mget"):
            ids = [document["_id"] for document in payload["docs"]]
            return _FakeResponse(
                {
                    "docs": [
                        {"_id": chunk_id, "found": chunk_id in self.existing_chunk_ids}
                        for chunk_id in ids
                    ]
                }
            )
        if http_request.full_url.endswith("/_refresh"):
            return _FakeResponse({"_shards": {"successful": 1}})
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
