import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_search.hybrid import HybridSearchOptions, hybrid_search_chunks  # noqa: E402


class HybridSearchTests(unittest.TestCase):
    def test_hybrid_search_combines_keyword_and_vector_hits(self) -> None:
        """Verify hybrid search returns the normal ranked chunk response shape.
        The first Phase 6 path should let callers switch from SQLite vector
        search to OpenSearch hybrid search without learning a new response
        contract.
        """
        with fake_opensearch_transport(), patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeQueryEmbedder(),
        ):
            response = hybrid_search_chunks(
                HybridSearchOptions(
                    query="clockwork garden",
                    opensearch_url="http://fake-opensearch.local",
                    index_name="librarian-test",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    genre="Science Fiction",
                    limit=5,
                )
            )

        self.assertEqual(response.query, "clockwork garden")
        self.assertEqual(response.candidate_count, 1)
        self.assertEqual(response.filters, {"genre": "Science Fiction"})
        self.assertEqual(response.results[0].chunk_id, "book-1:0")
        self.assertEqual(response.results[0].title, "The Clockwork Garden")
        self.assertGreater(response.results[0].score, 0)


@contextmanager
def fake_opensearch_transport():
    transport = _FakeOpenSearchTransport()
    with patch("urllib.request.urlopen", side_effect=transport.urlopen):
        yield transport


class _FakeOpenSearchTransport:
    def urlopen(self, http_request, timeout=None):
        if not http_request.full_url.endswith("/_search"):
            raise AssertionError(f"unexpected OpenSearch request: {http_request.full_url}")
        return _FakeResponse(
            {
                "hits": {
                    "hits": [
                        {
                            "_score": 2.0,
                            "_source": {
                                "chunk_id": "book-1:0",
                                "book_id": "book-1",
                                "relative_path": "book.epub",
                                "title": "The Clockwork Garden",
                                "authors": ["Test Author"],
                                "publisher": "Fixture Press",
                                "chunk_index": 0,
                                "text": "The clockwork garden woke at dawn.",
                                "embedding_provider": "ollama",
                                "embedding_model": "all-minilm",
                                "dimensions": 2,
                                "vector": [1.0, 0.0],
                                "tags": ["clockwork garden"],
                                "genres": ["Science Fiction"],
                            },
                        }
                    ]
                }
            }
        )


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeQueryEmbedder:
    provider = "ollama"
    model = "all-minilm"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]


if __name__ == "__main__":
    unittest.main()
