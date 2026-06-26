import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_recommendations.recommendations import (  # noqa: E402
    RecommendationOptions,
    recommend_books,
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


class RecommendationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_books()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_recommendations_rank_books_with_evidence_and_metadata(self) -> None:
        """Verify recommendations aggregate chunk search into book results.
        The recommendation response should be book-level, preserve evidence
        chunks for review, and enrich candidates with generated tags/genres so
        the eventual UI can explain why a book was recommended.
        """
        with fake_ollama_transport():
            response = recommend_books(
                RecommendationOptions(
                    query="thoughtful science fiction with clockwork gardens",
                    database_url=self.database_url,
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    ollama_base_url="http://fake-ollama.local",
                    limit=2,
                    retrieval_limit=4,
                )
            )

        self.assertEqual(response.candidate_count, 2)
        self.assertEqual(response.recommendations[0].book_id, "clockwork-book")
        self.assertEqual(response.recommendations[0].title, "The Clockwork Garden")
        self.assertIn("Science Fiction", response.recommendations[0].genres)
        self.assertIn("clockwork garden", response.recommendations[0].tags)
        self.assertEqual(response.recommendations[0].evidence[0].source_id, "R1.1")
        self.assertIn("recommend The Clockwork Garden", response.answer)

    def test_recommendations_can_filter_by_generated_genre_and_tag(self) -> None:
        """Verify recommendation filters can use derived book metadata.
        Phase 5 relies on generated tags and genres, so the recommendation layer
        should be able to narrow candidates by those fields after retrieval
        groups chunk matches into books.
        """
        with fake_ollama_transport():
            response = recommend_books(
                RecommendationOptions(
                    query="books about gardens",
                    database_url=self.database_url,
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    ollama_base_url="http://fake-ollama.local",
                    genre="Science Fiction",
                    tag="clockwork",
                )
            )

        self.assertEqual(response.candidate_count, 1)
        self.assertEqual(response.filters["genre"], "Science Fiction")
        self.assertEqual(response.filters["tag"], "clockwork")
        self.assertEqual(
            [item.book_id for item in response.recommendations],
            ["clockwork-book"],
        )

    def test_recommendations_explain_when_filters_remove_everything(self) -> None:
        """Verify users get a clear response when no books match.
        A recommendation query with overly narrow metadata filters should not
        try to hallucinate a fit; it should return an empty recommendation list
        with an actionable explanation.
        """
        with fake_ollama_transport():
            response = recommend_books(
                RecommendationOptions(
                    query="books about gardens",
                    database_url=self.database_url,
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    ollama_base_url="http://fake-ollama.local",
                    genre="Memoir",
                )
            )

        self.assertEqual(response.candidate_count, 0)
        self.assertEqual(response.recommendations, [])
        self.assertIn("No recommendation candidates matched", response.answer)

    def _seed_books(self) -> None:
        books = [
            BookRecord(
                id="clockwork-book",
                source_path="/books/clockwork.epub",
                relative_path="clockwork.epub",
                file_hash="clockwork-book",
                size_bytes=100,
                title="The Clockwork Garden",
                authors=["Test Author"],
                publisher="Fixture Press",
                status="ingested",
                ingested_at=utc_now(),
            ),
            BookRecord(
                id="ocean-book",
                source_path="/books/ocean.epub",
                relative_path="ocean.epub",
                file_hash="ocean-book",
                size_bytes=100,
                title="The Moonlit Ocean",
                authors=["Second Author"],
                publisher="Fixture Press",
                status="ingested",
                ingested_at=utc_now(),
            ),
        ]
        chunks = [
            ChunkRecord(
                id="clockwork-book:0",
                book_id="clockwork-book",
                chunk_index=0,
                text="The clockwork garden woke at dawn with brass birds.",
                character_count=54,
                token_estimate=11,
            ),
            ChunkRecord(
                id="clockwork-book:1",
                book_id="clockwork-book",
                chunk_index=1,
                text="The inventor wondered whether machines could grow.",
                character_count=52,
                token_estimate=9,
            ),
            ChunkRecord(
                id="ocean-book:0",
                book_id="ocean-book",
                chunk_index=0,
                text="The moonlit ocean carried old family memories.",
                character_count=47,
                token_estimate=8,
            ),
        ]
        embeddings = [
            EmbeddingRecord(
                id="clockwork-book:0:ollama:all-minilm",
                chunk_id="clockwork-book:0",
                provider="ollama",
                model="all-minilm",
                vector=[1.0, 0.0],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="clockwork-book:1:ollama:all-minilm",
                chunk_id="clockwork-book:1",
                provider="ollama",
                model="all-minilm",
                vector=[0.8, 0.2],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="ocean-book:0:ollama:all-minilm",
                chunk_id="ocean-book:0",
                provider="ollama",
                model="all-minilm",
                vector=[0.0, 1.0],
                dimensions=2,
            ),
        ]
        tags = [
            BookTagRecord(
                id="clockwork-book:tag",
                book_id="clockwork-book",
                tag="clockwork garden",
                tag_type="topic",
                source="llm",
                confidence=0.93,
                provider="ollama",
                model="llama3.2:3b",
                rationale="Core subject.",
            ),
            BookTagRecord(
                id="ocean-book:tag",
                book_id="ocean-book",
                tag="family memory",
                tag_type="topic",
                source="llm",
                confidence=0.88,
                provider="ollama",
                model="llama3.2:3b",
                rationale="Core subject.",
            ),
        ]
        genres = [
            BookGenreRecord(
                id="clockwork-book:genre",
                book_id="clockwork-book",
                genre="Science Fiction",
                genre_role="primary",
                source="llm",
                confidence=0.91,
                provider="ollama",
                model="llama3.2:3b",
                rationale="Speculative machinery.",
            ),
            BookGenreRecord(
                id="ocean-book:genre",
                book_id="ocean-book",
                genre="Literary Fiction",
                genre_role="primary",
                source="llm",
                confidence=0.9,
                provider="ollama",
                model="llama3.2:3b",
                rationale="Memory-driven story.",
            ),
        ]
        with SQLiteIngestionStore(self.database_path) as store:
            for book in books:
                store.save_book_with_chunks(
                    book,
                    [chunk for chunk in chunks if chunk.book_id == book.id],
                )
            store.save_chunk_embeddings(embeddings)
            store.save_book_tags(tags)
            store.save_book_genres(genres)


@contextmanager
def fake_ollama_transport():
    transport = _FakeOllamaTransport()
    with patch("urllib.request.urlopen", side_effect=transport.urlopen):
        yield transport


class _FakeOllamaTransport:
    def urlopen(self, http_request, timeout=None):
        payload = json.loads(http_request.data.decode("utf-8"))
        if http_request.full_url.endswith("/api/embed"):
            inputs = payload.get("input", [])
            return _FakeResponse(
                {
                    "model": payload.get("model"),
                    "embeddings": [_embedding_for_text(str(text)) for text in inputs],
                }
            )
        if http_request.full_url.endswith("/api/chat"):
            return _FakeResponse(
                {
                    "model": payload.get("model"),
                    "message": {
                        "role": "assistant",
                        "content": (
                            "I would recommend The Clockwork Garden because the "
                            "retrieved evidence and generated metadata both match. [R1.1]"
                        ),
                    },
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
    if "clockwork" in normalized or "garden" in normalized or "science" in normalized:
        return [1.0, 0.0]
    if "ocean" in normalized or "memory" in normalized:
        return [0.0, 1.0]
    return [0.5, 0.5]


if __name__ == "__main__":
    unittest.main()
