import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.ingestion.fixtures import SAMPLE_EPUB, SAMPLE_EPUB_SHA256, SAMPLE_PUBLISHER

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_ingestion.chunk import chunk_text
from librarian_config.config import (
    resolve_embedding_model,
    resolve_embedding_provider,
    resolve_ollama_base_url,
    resolve_database_url,
    sqlite_path_from_url,
)
from librarian_ingestion.epub import parse_epub
from librarian_storage.storage import (
    BookGenreRecord,
    BookTagRecord,
    BookSummaryRecord,
    BookRecord,
    ChapterSummaryRecord,
    ChunkRecord,
    EmbeddingRecord,
    SQLiteIngestionStore,
    SummaryJobRecord,
    build_book_identity_key,
    create_ingestion_store,
    utc_now,
)


class DatabaseConfigTests(unittest.TestCase):
    def test_resolve_database_url_uses_env_then_default(self) -> None:
        """Verify database configuration follows the same env-first pattern.
        This lets local development use the default SQLite file while tests and
        future deployments can point storage somewhere else.
        """
        self.assertEqual(
            resolve_database_url(env={"LIBRARIAN_DATABASE_URL": "sqlite:///tmp.db"}),
            "sqlite:///tmp.db",
        )
        self.assertEqual(resolve_database_url(env={}), "sqlite:///data/librarian.db")

    def test_resolve_embedding_config_tracks_local_provider_settings(self) -> None:
        """Verify embedding settings are configurable but harmless by default.
        The repo can remember that Ollama is the likely provider while default
        ingestion still avoids any model download or network call.
        """
        env = {
            "LIBRARIAN_EMBEDDING_PROVIDER": "ollama",
            "LIBRARIAN_EMBEDDING_MODEL": "all-minilm",
            "LIBRARIAN_OLLAMA_BASE_URL": "http://localhost:11434/",
        }

        self.assertEqual(resolve_embedding_provider(env=env), "ollama")
        self.assertEqual(resolve_embedding_model(env=env), "all-minilm")
        self.assertEqual(resolve_ollama_base_url(env=env), "http://localhost:11434")
        self.assertEqual(resolve_embedding_provider(env={}), "noop")

    def test_sqlite_path_from_url_accepts_relative_and_absolute_paths(self) -> None:
        """Verify SQLite URL parsing supports common local paths.
        The CLI accepts database URLs, but the SQLite adapter needs filesystem
        paths, so this test protects that translation.
        """
        self.assertEqual(sqlite_path_from_url("sqlite:///data/test.db"), Path("data/test.db"))
        self.assertEqual(sqlite_path_from_url("sqlite:////tmp/test.db"), Path("/tmp/test.db"))

    def test_sqlite_path_from_url_rejects_non_sqlite_url(self) -> None:
        """Verify SQLite-specific parsing refuses other database schemes.
        This keeps adapter selection explicit instead of accidentally treating a
        Postgres URL like a broken file path.
        """
        with self.assertRaises(ValueError):
            sqlite_path_from_url("postgresql://localhost/librarian")

    def test_create_ingestion_store_rejects_unimplemented_postgres(self) -> None:
        """Verify the adapter factory recognizes Postgres but blocks it for now.
        This documents the planned extension point while preventing callers from
        believing Postgres persistence already exists.
        """
        with self.assertRaises(NotImplementedError):
            create_ingestion_store("postgresql://localhost/librarian")

    def test_book_identity_key_uses_title_author_and_publisher(self) -> None:
        """Verify duplicate detection normalizes stable book metadata.
        Different casing or spacing should not hide duplicate books, while a
        different publisher can represent a distinct edition/source.
        """
        original = build_book_identity_key(
            "The Clockwork Garden", ["Test Author"], "Fixture Press"
        )
        normalized = build_book_identity_key(
            " the   clockwork garden ", ["test author"], "fixture press"
        )
        different_publisher = build_book_identity_key(
            "The Clockwork Garden", ["Test Author"], "Other Press"
        )

        self.assertEqual(original, normalized)
        self.assertNotEqual(original, different_publisher)


class SQLiteIngestionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_book_with_chunks_persists_book_and_chunks(self) -> None:
        """Verify the SQLite adapter persists the core ingestion records.
        This stores a parsed fixture book and its chunks, then reads them back
        through both the adapter and raw SQL to protect the schema contract.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        chunks = chunk_text(parsed.text, target_size=120, overlap=20)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )
        chunk_records = [
            ChunkRecord(
                id=f"{SAMPLE_EPUB_SHA256}:{chunk.chunk_index}",
                book_id=SAMPLE_EPUB_SHA256,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                character_count=chunk.character_count,
                token_estimate=chunk.token_estimate,
            )
            for chunk in chunks
        ]

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, chunk_records)

            self.assertEqual(store.count_books(), 1)
            self.assertEqual(store.count_chunks(), len(chunks))
            stored = store.get_book_by_relative_path("sample.epub")

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.file_hash, SAMPLE_EPUB_SHA256)
        self.assertEqual(stored.status, "ingested")
        self.assertEqual(stored.chunk_count, len(chunks))

        with sqlite3.connect(self.database_path) as connection:
            title, authors_json, publisher = connection.execute(
                "SELECT title, authors_json, publisher FROM books WHERE relative_path = ?",
                ("sample.epub",),
            ).fetchone()
            first_chunk = connection.execute(
                "SELECT text FROM chunks WHERE book_id = ? ORDER BY chunk_index LIMIT 1",
                (SAMPLE_EPUB_SHA256,),
            ).fetchone()[0]

        self.assertEqual(title, "The Clockwork Garden")
        self.assertIn("Test Author", authors_json)
        self.assertEqual(publisher, SAMPLE_PUBLISHER)
        self.assertIn("The clockwork garden woke at dawn.", first_chunk)

    def test_summary_and_book_listing_support_read_clients(self) -> None:
        """Verify desktop/API clients can inspect stored ingestion state.
        The summary and listing helpers provide read models without requiring
        callers to know the SQLite schema.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])

            summary = store.get_summary()
            books = store.list_books()

        self.assertEqual(summary.total_books, 1)
        self.assertEqual(summary.status_counts["ingested"], 1)
        self.assertEqual(books[0].title, "The Clockwork Garden")
        self.assertEqual(books[0].authors, ["Test Author"])

    def test_save_chunk_embeddings_persists_provider_model_and_vector(self) -> None:
        """Verify chunk embeddings are stored as local runtime data.
        Model weights stay outside the repo, but the database records which
        provider/model produced each vector so future retrieval is reproducible.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )
        chunk = ChunkRecord(
            id=f"{SAMPLE_EPUB_SHA256}:0",
            book_id=SAMPLE_EPUB_SHA256,
            chunk_index=0,
            text="The clockwork garden woke at dawn.",
            character_count=35,
            token_estimate=8,
        )
        embedding = EmbeddingRecord(
            id=f"{chunk.id}:ollama:all-minilm",
            chunk_id=chunk.id,
            provider="ollama",
            model="all-minilm",
            vector=[0.1, 0.2, 0.3],
            dimensions=3,
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [chunk])
            store.save_chunk_embeddings([embedding])
            summary = store.get_summary()
            embeddings = store.list_embeddings()
            embedding_models = store.get_embedding_model_summaries()

        self.assertEqual(summary.total_embeddings, 1)
        self.assertEqual(embeddings[0].chunk_id, chunk.id)
        self.assertEqual(embeddings[0].relative_path, "sample.epub")
        self.assertEqual(embeddings[0].vector_sample, [0.1, 0.2, 0.3])
        self.assertIn("The clockwork garden", embeddings[0].text_preview)
        self.assertEqual(embedding_models[0].provider, "ollama")
        self.assertEqual(embedding_models[0].embedding_count, 1)

        with sqlite3.connect(self.database_path) as connection:
            provider, model, dimensions, vector_json = connection.execute(
                """
                SELECT provider, model, dimensions, vector_json
                FROM chunk_embeddings
                WHERE chunk_id = ?
                """,
                (chunk.id,),
            ).fetchone()

        self.assertEqual(provider, "ollama")
        self.assertEqual(model, "all-minilm")
        self.assertEqual(dimensions, 3)
        self.assertEqual(vector_json, "[0.1, 0.2, 0.3]")

    def test_summary_records_can_be_saved_reused_and_deleted(self) -> None:
        """Verify generated summaries are scoped by book/provider/model/detail.
        This lets us rebuild summaries when swapping Ollama and Codex without
        deleting source chunks or embeddings.
        """
        book = BookRecord(
            id="book-1",
            source_path="/books/forward.epub",
            relative_path="forward.epub",
            file_hash="book-1",
            size_bytes=100,
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            status="ingested",
            ingested_at=utc_now(),
        )
        chunks = [
            ChunkRecord(
                id="book-1:0",
                book_id="book-1",
                chunk_index=0,
                chapter_title="Part One",
                text="Hari Seldon studies psychohistory.",
                character_count=35,
                token_estimate=8,
            )
        ]
        chapter_summary = ChapterSummaryRecord(
            id="chapter-summary-1",
            book_id="book-1",
            chapter_key="chapter-001",
            chapter_title="Part One",
            chunk_start_index=0,
            chunk_end_index=0,
            provider="codex",
            model="codex",
            detail="medium",
            source_hash="abc",
            summary="Seldon works on psychohistory.",
        )
        book_summary = BookSummaryRecord(
            id="book-summary-1",
            book_id="book-1",
            provider="codex",
            model="codex",
            detail="medium",
            source_hash="def",
            summary="A book about Seldon and psychohistory.",
            chapter_summary_count=1,
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, chunks)
            store.save_chapter_summary(chapter_summary)
            store.save_book_summary(book_summary)

            stored_book = store.get_summary_book("book-1")
            stored_chunks = store.list_book_summary_chunks("book-1")
            stored_chapter = store.get_chapter_summary(
                book_id="book-1",
                chapter_key="chapter-001",
                provider="codex",
                model="codex",
                detail="medium",
            )
            stored_summary = store.get_book_summary(
                book_id="book-1",
                provider="codex",
                model="codex",
                detail="medium",
            )
            deleted = store.delete_summaries(
                book_id="book-1",
                provider="codex",
                model="codex",
                detail="medium",
            )

        self.assertIsNotNone(stored_book)
        assert stored_book is not None
        self.assertEqual(stored_book.title, "Forward the Foundation")
        self.assertEqual(stored_chunks[0].chapter_title, "Part One")
        self.assertIsNotNone(stored_chapter)
        assert stored_chapter is not None
        self.assertEqual(stored_chapter.summary, "Seldon works on psychohistory.")
        self.assertIsNotNone(stored_summary)
        assert stored_summary is not None
        self.assertEqual(stored_summary.chapter_summary_count, 1)
        self.assertEqual(deleted, 2)

    def test_summary_jobs_can_be_queued_listed_and_updated(self) -> None:
        """Verify ingestion can queue durable summary work without running it.
        The job row records provider/model/detail and status so a separate
        worker can generate summaries after ingestion returns.
        """
        book = BookRecord(
            id="book-1",
            source_path="/books/forward.epub",
            relative_path="forward.epub",
            file_hash="book-1",
            size_bytes=100,
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            status="ingested",
            ingested_at=utc_now(),
        )
        original_job = SummaryJobRecord(
            id="summary-job-1",
            book_id="book-1",
            provider="CODEX",
            model="codex",
            detail="MEDIUM",
        )
        refreshed_job = SummaryJobRecord(
            id="summary-job-1-refreshed",
            book_id="book-1",
            provider="codex",
            model="codex",
            detail="medium",
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_summary_job(original_job)
            store.save_summary_job(refreshed_job)

            pending_jobs = store.list_summary_jobs(status="pending")
            store.update_summary_job(
                "summary-job-1-refreshed",
                status="failed",
                attempts=1,
                error_message="summary service unavailable",
            )
            failed_jobs = store.list_summary_jobs(status="failed")

        self.assertEqual(len(pending_jobs), 1)
        self.assertEqual(pending_jobs[0].id, "summary-job-1-refreshed")
        self.assertEqual(pending_jobs[0].provider, "codex")
        self.assertEqual(pending_jobs[0].detail, "medium")
        self.assertEqual(pending_jobs[0].title, "Forward the Foundation")
        self.assertEqual(failed_jobs[0].attempts, 1)
        self.assertEqual(failed_jobs[0].error_message, "summary service unavailable")

    def test_book_tags_can_be_saved_updated_filtered_and_deleted(self) -> None:
        """Verify book tags are stored with provenance and replace cleanly.
        Tags will be generated by later LLM workflows, so this storage layer
        needs to preserve source/provider metadata and support rebuild deletes.
        """
        book = BookRecord(
            id="book-1",
            source_path="/books/forward.epub",
            relative_path="forward.epub",
            file_hash="book-1",
            size_bytes=100,
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            status="ingested",
            ingested_at=utc_now(),
        )
        original_tag = BookTagRecord(
            id="tag-1",
            book_id="book-1",
            tag="Psychohistory",
            tag_type="topic",
            source="llm",
            confidence=0.82,
            provider="codex",
            model="codex",
            rationale="Central idea across the book.",
        )
        updated_tag = BookTagRecord(
            id="tag-1-updated",
            book_id="book-1",
            tag=" psychohistory ",
            tag_type="TOPIC",
            source="LLM",
            confidence=0.91,
            provider="codex",
            model="codex",
            rationale="The core scientific and political concept.",
        )
        theme_tag = BookTagRecord(
            id="tag-2",
            book_id="book-1",
            tag="political decline",
            tag_type="theme",
            source="llm",
            confidence=0.74,
            provider="codex",
            model="codex",
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_book_tags([original_tag])
            store.save_book_tags([updated_tag, theme_tag])

            all_tags = store.list_book_tags(book_id="book-1")
            topic_tags = store.list_book_tags(book_id="book-1", tag_type="topic")
            deleted_topics = store.delete_book_tags(book_id="book-1", tag_type="topic")
            remaining_tags = store.list_book_tags(book_id="book-1")

        self.assertEqual(len(all_tags), 2)
        self.assertEqual(len(topic_tags), 1)
        self.assertEqual(topic_tags[0].id, "tag-1-updated")
        self.assertEqual(topic_tags[0].tag, "psychohistory")
        self.assertEqual(topic_tags[0].tag_type, "topic")
        self.assertEqual(topic_tags[0].source, "llm")
        self.assertEqual(topic_tags[0].confidence, 0.91)
        self.assertEqual(topic_tags[0].provider, "codex")
        self.assertEqual(topic_tags[0].model, "codex")
        self.assertEqual(deleted_topics, 1)
        self.assertEqual([tag.tag for tag in remaining_tags], ["political decline"])

    def test_book_tags_are_removed_when_book_is_deleted(self) -> None:
        """Verify tag records follow the book lifecycle.
        Book tags are derived metadata, so deleting or replacing a book must not
        leave orphaned tag rows behind in the local database.
        """
        first_book = BookRecord(
            id="book-1",
            source_path="/books/old.epub",
            relative_path="same.epub",
            file_hash="book-1",
            size_bytes=100,
            title="First Version",
            authors=["Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        replacement_book = BookRecord(
            id="book-2",
            source_path="/books/new.epub",
            relative_path="same.epub",
            file_hash="book-2",
            size_bytes=100,
            title="Second Version",
            authors=["Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        tag = BookTagRecord(
            id="tag-1",
            book_id="book-1",
            tag="old metadata",
            tag_type="topic",
            source="manual",
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(first_book, [])
            store.save_book_tags([tag])
            store.save_book_with_chunks(replacement_book, [])

            old_tags = store.list_book_tags(book_id="book-1")
            new_tags = store.list_book_tags(book_id="book-2")

        self.assertEqual(old_tags, [])
        self.assertEqual(new_tags, [])

    def test_book_genres_can_be_saved_updated_filtered_and_deleted(self) -> None:
        """Verify book genres are stored as structured derived metadata.
        Genres are related to tags, but they have their own primary/secondary
        role semantics, so storage should not force them into generic tag rows.
        """
        book = BookRecord(
            id="book-1",
            source_path="/books/forward.epub",
            relative_path="forward.epub",
            file_hash="book-1",
            size_bytes=100,
            title="Forward the Foundation",
            authors=["Isaac Asimov"],
            status="ingested",
            ingested_at=utc_now(),
        )
        original_genre = BookGenreRecord(
            id="genre-1",
            book_id="book-1",
            genre="Science Fiction",
            genre_role="primary",
            source="llm",
            confidence=0.82,
            provider="codex",
            model="codex",
            rationale="The book is part of the Foundation science fiction arc.",
        )
        updated_genre = BookGenreRecord(
            id="genre-1-updated",
            book_id="book-1",
            genre=" science fiction ",
            genre_role="PRIMARY",
            source="LLM",
            confidence=0.94,
            provider="codex",
            model="codex",
            rationale="The core genre is Foundation-era science fiction.",
        )
        secondary_genre = BookGenreRecord(
            id="genre-2",
            book_id="book-1",
            genre="Political Fiction",
            genre_role="secondary",
            source="llm",
            confidence=0.71,
            provider="codex",
            model="codex",
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_book_genres([original_genre])
            store.save_book_genres([updated_genre, secondary_genre])

            all_genres = store.list_book_genres(book_id="book-1")
            primary_genres = store.list_book_genres(
                book_id="book-1", genre_role="primary"
            )
            deleted_primary = store.delete_book_genres(
                book_id="book-1", genre_role="primary"
            )
            remaining_genres = store.list_book_genres(book_id="book-1")

        self.assertEqual(len(all_genres), 2)
        self.assertEqual(len(primary_genres), 1)
        self.assertEqual(primary_genres[0].id, "genre-1-updated")
        self.assertEqual(primary_genres[0].genre, "science fiction")
        self.assertEqual(primary_genres[0].genre_role, "primary")
        self.assertEqual(primary_genres[0].source, "llm")
        self.assertEqual(primary_genres[0].confidence, 0.94)
        self.assertEqual(primary_genres[0].provider, "codex")
        self.assertEqual(primary_genres[0].model, "codex")
        self.assertEqual(deleted_primary, 1)
        self.assertEqual([genre.genre for genre in remaining_genres], ["Political Fiction"])

    def test_book_genres_are_removed_when_book_is_deleted(self) -> None:
        """Verify genre records follow the book lifecycle.
        Genres are generated from book summaries, so replacing an EPUB should
        clear stale genre rows exactly like summaries and topic tags.
        """
        first_book = BookRecord(
            id="book-1",
            source_path="/books/old.epub",
            relative_path="same.epub",
            file_hash="book-1",
            size_bytes=100,
            title="First Version",
            authors=["Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        replacement_book = BookRecord(
            id="book-2",
            source_path="/books/new.epub",
            relative_path="same.epub",
            file_hash="book-2",
            size_bytes=100,
            title="Second Version",
            authors=["Author"],
            status="ingested",
            ingested_at=utc_now(),
        )
        genre = BookGenreRecord(
            id="genre-1",
            book_id="book-1",
            genre="old genre",
            genre_role="primary",
            source="manual",
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(first_book, [])
            store.save_book_genres([genre])
            store.save_book_with_chunks(replacement_book, [])

            old_genres = store.list_book_genres(book_id="book-1")
            new_genres = store.list_book_genres(book_id="book-2")

        self.assertEqual(old_genres, [])
        self.assertEqual(new_genres, [])

    def test_get_book_by_identity_finds_existing_book_metadata(self) -> None:
        """Verify the adapter can find an already ingested book by metadata.
        This is the guardrail that prevents a different file hash of the same
        title, author, and publisher from being ingested as another full book.
        """
        parsed = parse_epub(SAMPLE_EPUB)
        book = BookRecord(
            id=SAMPLE_EPUB_SHA256,
            source_path=str(SAMPLE_EPUB),
            relative_path="sample.epub",
            file_hash=SAMPLE_EPUB_SHA256,
            size_bytes=SAMPLE_EPUB.stat().st_size,
            title=parsed.title,
            authors=parsed.authors,
            status="ingested",
            publisher=parsed.publisher,
            ingested_at=utc_now(),
        )

        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])

            stored = store.get_book_by_identity(
                " the clockwork garden ", ["test author"], SAMPLE_PUBLISHER
            )
            different_publisher = store.get_book_by_identity(
                "The Clockwork Garden", ["Test Author"], "Other Press"
            )

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.relative_path, "sample.epub")
        self.assertIsNone(different_publisher)


if __name__ == "__main__":
    unittest.main()
