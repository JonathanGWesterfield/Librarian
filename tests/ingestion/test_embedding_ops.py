import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.embedding_ops import (
    EmbedQueryOptions,
    RebuildEmbeddingsOptions,
    embed_query,
    rebuild_embeddings,
)
from librarian_ingestion.storage import (
    BookRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    utc_now,
)


class RebuildEmbeddingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rebuild_embeddings_resets_vectors_without_deleting_chunks(self) -> None:
        """Verify benchmark rebuilds only touch embedding rows.
        The raw chunk text is the stable source of truth, so resetting a model's
        vectors must leave books and chunks intact for fast re-embedding.
        """
        self._seed_book_chunk_and_embedding()

        with patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeEmbedder(),
        ):
            result = rebuild_embeddings(
                RebuildEmbeddingsOptions(
                    database_url=self.database_url,
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    reset=True,
                    batch_size=2,
                )
            )

        self.assertEqual(result.chunks_seen, 1)
        self.assertEqual(result.embeddings_deleted, 1)
        self.assertEqual(result.embeddings_stored, 1)
        self.assertEqual(result.total_embeddings, 1)

        with sqlite3.connect(self.database_path) as connection:
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            vector_json = connection.execute(
                "SELECT vector_json FROM chunk_embeddings"
            ).fetchone()[0]

        self.assertEqual(chunk_count, 1)
        self.assertEqual(vector_json, "[0.9, 0.8, 0.7]")

    def _seed_book_chunk_and_embedding(self) -> None:
        book = BookRecord(
            id="book-hash",
            source_path="/books/sample.epub",
            relative_path="sample.epub",
            file_hash="book-hash",
            size_bytes=100,
            title="Sample",
            authors=["Test Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        chunk = ChunkRecord(
            id="book-hash:0",
            book_id="book-hash",
            chunk_index=0,
            text="The raw text stays here.",
            character_count=24,
            token_estimate=6,
        )
        embedding = EmbeddingRecord(
            id="book-hash:0:ollama:all-minilm",
            chunk_id="book-hash:0",
            provider="ollama",
            model="all-minilm",
            vector=[0.1, 0.2, 0.3],
            dimensions=3,
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [chunk])
            store.save_chunk_embeddings([embedding])


class EmbedQueryTests(unittest.TestCase):
    def test_embed_query_generates_one_vector_for_user_text(self) -> None:
        """Verify query embedding uses the same provider abstraction as chunks.
        Retrieval will use this vector to compare the user's query against
        stored chunk embeddings, so it should preserve provider/model metadata.
        """
        with patch(
            "librarian_ingestion.embedding_ops.create_configured_embedder",
            return_value=_FakeEmbedder(),
        ):
            result = embed_query(
                EmbedQueryOptions(
                    query="  clockwork gardens  ",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                )
            )

        self.assertEqual(result.query, "clockwork gardens")
        self.assertEqual(result.embedding_provider, "ollama")
        self.assertEqual(result.embedding_model, "all-minilm")
        self.assertEqual(result.dimensions, 3)
        self.assertEqual(result.vector, [0.9, 0.8, 0.7])

    def test_embed_query_rejects_empty_text(self) -> None:
        """Verify empty user queries fail before touching the embedder.
        Search should not generate meaningless vectors for blank input.
        """
        with self.assertRaises(ValueError):
            embed_query(EmbedQueryOptions(query="  "))


class _FakeEmbedder:
    provider = "ollama"
    model = "all-minilm"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.9, 0.8, 0.7] for _text in texts]


if __name__ == "__main__":
    unittest.main()
