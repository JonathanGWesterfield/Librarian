import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.search import SearchOptions, search_chunks
from librarian_ingestion.storage import (
    BookRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    utc_now,
)


class SearchChunksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self._seed_search_fixture()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_chunks_ranks_stored_embeddings_by_cosine_similarity(self) -> None:
        """Verify SQLite retrieval compares every stored chunk vector.
        This is the first simple baseline search path: embed the query, load
        matching chunk embeddings, score with NumPy cosine similarity, then
        return the best chunks with source metadata.
        """
        with patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeQueryEmbedder(),
        ):
            response = search_chunks(
                SearchOptions(
                    query="clockwork garden",
                    database_url=self.database_url,
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    limit=2,
                )
            )

        self.assertEqual(response.query, "clockwork garden")
        self.assertEqual(response.candidate_count, 3)
        self.assertEqual(len(response.results), 2)
        self.assertEqual(response.results[0].chunk_id, "book-hash:0")
        self.assertAlmostEqual(response.results[0].score, 1.0, places=6)
        self.assertEqual(response.results[0].relative_path, "sample.epub")
        self.assertIn("clockwork garden", response.results[0].text)
        self.assertEqual(response.results[1].chunk_id, "book-hash:2")

    def test_search_chunks_ignores_vectors_with_wrong_dimensions(self) -> None:
        """Verify malformed or stale vectors are skipped during scoring.
        This prevents one bad embedding row from breaking the entire retrieval
        path while we are still using JSON vectors in SQLite.
        """
        with patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeQueryEmbedder(),
        ):
            response = search_chunks(
                SearchOptions(
                    query="clockwork garden",
                    database_url=self.database_url,
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    limit=10,
                )
            )

        self.assertEqual(response.candidate_count, 3)
        self.assertNotIn(
            "book-hash:bad",
            [result.chunk_id for result in response.results],
        )

    def _seed_search_fixture(self) -> None:
        book = BookRecord(
            id="book-hash",
            source_path="/books/sample.epub",
            relative_path="sample.epub",
            file_hash="book-hash",
            size_bytes=100,
            title="Sample Book",
            authors=["Test Author"],
            publisher="Fixture Press",
            status="ingested",
            ingested_at=utc_now(),
        )
        chunks = [
            ChunkRecord(
                id="book-hash:0",
                book_id="book-hash",
                chunk_index=0,
                text="The clockwork garden woke at dawn.",
                character_count=35,
                token_estimate=8,
            ),
            ChunkRecord(
                id="book-hash:1",
                book_id="book-hash",
                chunk_index=1,
                text="A distant ocean rolled under moonlight.",
                character_count=39,
                token_estimate=9,
            ),
            ChunkRecord(
                id="book-hash:2",
                book_id="book-hash",
                chunk_index=2,
                text="The brass robin counted silver seeds.",
                character_count=38,
                token_estimate=9,
            ),
            ChunkRecord(
                id="book-hash:bad",
                book_id="book-hash",
                chunk_index=3,
                text="This vector has the wrong dimensions.",
                character_count=37,
                token_estimate=9,
            ),
        ]
        embeddings = [
            EmbeddingRecord(
                id="book-hash:0:ollama:all-minilm",
                chunk_id="book-hash:0",
                provider="ollama",
                model="all-minilm",
                vector=[1.0, 0.0],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="book-hash:1:ollama:all-minilm",
                chunk_id="book-hash:1",
                provider="ollama",
                model="all-minilm",
                vector=[0.0, 1.0],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="book-hash:2:ollama:all-minilm",
                chunk_id="book-hash:2",
                provider="ollama",
                model="all-minilm",
                vector=[0.7, 0.7],
                dimensions=2,
            ),
            EmbeddingRecord(
                id="book-hash:bad:ollama:all-minilm",
                chunk_id="book-hash:bad",
                provider="ollama",
                model="all-minilm",
                vector=[1.0, 0.0, 0.0],
                dimensions=3,
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


if __name__ == "__main__":
    unittest.main()
