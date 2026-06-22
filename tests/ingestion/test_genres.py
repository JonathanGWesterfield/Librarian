from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.generation import ChatMessage
from librarian_metadata.genres import (
    DeleteBookGenresOptions,
    GenerateBookGenresOptions,
    ListBookGenresOptions,
    delete_book_genres,
    generate_book_genres,
    list_book_genres,
)
from librarian_storage.storage import (
    BookRecord,
    BookSummaryRecord,
    SQLiteIngestionStore,
    utc_now,
)


class _FakeGenerator:
    provider = "codex"
    model = "codex"

    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[ChatMessage] = []
        self.response_format: str | None = None

    def generate(
        self, messages: list[ChatMessage], *, response_format: str | None = None
    ) -> str:
        self.messages = messages
        self.response_format = response_format
        return self.response


class BookGenreGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_book_genres_from_existing_summary(self) -> None:
        """Verify genres are generated from stored book summaries.
        This protects the first genre workflow without calling Codex or Ollama,
        while still checking prompt shape, role parsing, and storage writes.
        """
        self._seed_book_summary()
        generator = _FakeGenerator(
            json.dumps(
                {
                    "primary_genre": {
                        "genre": "Science Fiction",
                        "confidence": 0.96,
                        "rationale": "Foundation is a science fiction series.",
                    },
                    "secondary_genres": [
                        {
                            "genre": "Political Fiction",
                            "confidence": 0.74,
                            "rationale": "Imperial politics shape the story.",
                        },
                        {
                            "genre": "science fiction",
                            "confidence": 0.5,
                            "rationale": "Duplicate should be ignored.",
                        },
                    ],
                }
            )
        )

        with patch(
            "librarian_metadata.genres.create_configured_generator",
            return_value=generator,
        ):
            result = generate_book_genres(
                GenerateBookGenresOptions(
                    database_url=self.database_url,
                    book_title="Forward the Foundation",
                    author="Isaac Asimov",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )

        with SQLiteIngestionStore(self.database_path) as store:
            stored_genres = store.list_book_genres(book_id="book-1")

        self.assertEqual(result.generated_genres, 2)
        self.assertEqual(result.cached_genres, 0)
        self.assertEqual(
            [(genre.genre, genre.genre_role) for genre in result.genres],
            [("Science Fiction", "primary"), ("Political Fiction", "secondary")],
        )
        self.assertEqual(stored_genres[0].provider, "codex")
        self.assertEqual(stored_genres[0].genre_role, "primary")
        self.assertIn("broad bookstore/library genres", generator.messages[0].content)
        self.assertIn("primary_genre", generator.messages[1].content)
        self.assertIn("Return only the completed JSON object", generator.messages[1].content)
        self.assertEqual(generator.response_format, "json")

    def test_generate_book_genres_reuses_cached_genres(self) -> None:
        """Verify repeated genre generation can avoid another LLM call.
        Generated genres should be cached by provider/model so benchmarking can
        avoid accidental regeneration unless force-refresh or reset is selected.
        """
        self._seed_book_summary()
        generator = _FakeGenerator(
            json.dumps(
                {
                    "primary_genre": {
                        "genre": "Science Fiction",
                        "confidence": 0.96,
                        "rationale": "Foundation is a science fiction series.",
                    },
                    "secondary_genres": [],
                }
            )
        )

        with patch(
            "librarian_metadata.genres.create_configured_generator",
            return_value=generator,
        ):
            generated = generate_book_genres(
                GenerateBookGenresOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )
            cached = generate_book_genres(
                GenerateBookGenresOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )

        self.assertEqual(generated.generated_genres, 1)
        self.assertEqual(cached.generated_genres, 0)
        self.assertEqual(cached.cached_genres, 1)
        self.assertTrue(cached.genres[0].cached)

    def test_generate_book_genres_requires_existing_summary(self) -> None:
        """Verify genre generation fails before calling an LLM without summary.
        Genres are derived from book-level summaries, so the service should give
        a local error instead of trying to classify raw database state.
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
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])

        with self.assertRaisesRegex(ValueError, "book summary not found"):
            generate_book_genres(
                GenerateBookGenresOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    generation_provider="noop",
                    source_summary_provider="noop",
                    source_summary_model="noop",
                )
            )

    def test_generate_book_genres_rejects_invalid_generator_json(self) -> None:
        """Verify malformed LLM output is rejected before persistence.
        The service does not trust LLM text directly; it requires valid JSON
        with a usable primary genre before writing metadata.
        """
        self._seed_book_summary()
        generator = _FakeGenerator("not json")

        with patch(
            "librarian_metadata.genres.create_configured_generator",
            return_value=generator,
        ):
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                generate_book_genres(
                    GenerateBookGenresOptions(
                        database_url=self.database_url,
                        book_id="book-1",
                        source_summary_provider="codex",
                        source_summary_model="codex",
                        force_refresh=True,
                    )
                )

        with SQLiteIngestionStore(self.database_path) as store:
            self.assertEqual(store.list_book_genres(book_id="book-1"), [])

    def test_list_and_delete_book_genres_use_book_filters(self) -> None:
        """Verify genre inspection and cleanup can target a resolved book.
        The future CLI should use title/author filters without duplicating
        storage lookup logic or risking accidental library-wide deletion.
        """
        self._seed_book_summary()
        generator = _FakeGenerator(
            json.dumps(
                {
                    "primary_genre": {
                        "genre": "Science Fiction",
                        "confidence": 0.96,
                        "rationale": "Foundation is a science fiction series.",
                    },
                    "secondary_genres": [
                        {
                            "genre": "Political Fiction",
                            "confidence": 0.74,
                            "rationale": "Imperial politics shape the story.",
                        }
                    ],
                }
            )
        )
        with patch(
            "librarian_metadata.genres.create_configured_generator",
            return_value=generator,
        ):
            generate_book_genres(
                GenerateBookGenresOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )

        listed = list_book_genres(
            ListBookGenresOptions(
                database_url=self.database_url,
                book_title="Forward the Foundation",
                author="Isaac Asimov",
                genre_role="primary",
                source="llm",
                provider="codex",
                model="codex",
            )
        )
        deleted = delete_book_genres(
            DeleteBookGenresOptions(
                database_url=self.database_url,
                book_title="Forward the Foundation",
                author="Isaac Asimov",
            )
        )
        remaining = list_book_genres(
            ListBookGenresOptions(database_url=self.database_url, book_id="book-1")
        )

        self.assertEqual([genre.genre for genre in listed], ["Science Fiction"])
        self.assertEqual(deleted, 2)
        self.assertEqual(remaining, [])

    def test_delete_book_genres_requires_book_filter(self) -> None:
        """Verify genre deletion has a guardrail against library-wide deletes.
        An explicit all-library delete can be added later if needed, but this
        first service should require a book target for destructive operations.
        """
        with self.assertRaisesRegex(ValueError, "requires --book-id or --book-title"):
            delete_book_genres(DeleteBookGenresOptions(database_url=self.database_url))

    def _seed_book_summary(self) -> None:
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
        summary = BookSummaryRecord(
            id="summary-1",
            book_id="book-1",
            provider="codex",
            model="codex",
            detail="medium",
            source_hash="source",
            summary=(
                "Hari Seldon develops psychohistory while navigating political "
                "decline across the Galactic Empire."
            ),
            chapter_summary_count=2,
        )
        with SQLiteIngestionStore(self.database_path) as store:
            store.save_book_with_chunks(book, [])
            store.save_book_summary(summary)


if __name__ == "__main__":
    unittest.main()
