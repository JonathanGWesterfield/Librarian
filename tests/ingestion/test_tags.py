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
from librarian_metadata.tags import GenerateBookTagsOptions, generate_book_tags
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

    def generate(self, messages: list[ChatMessage]) -> str:
        self.messages = messages
        return self.response


class BookTagGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "librarian.db"
        self.database_url = f"sqlite:///{self.database_path}"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_book_tags_from_existing_summary(self) -> None:
        """Verify topic tags are generated from stored book summaries.
        This protects the first tag workflow without making tests call Codex or
        Ollama, while still checking that prompt output is validated and stored.
        """
        self._seed_book_summary()
        generator = _FakeGenerator(
            json.dumps(
                {
                    "tags": [
                        {
                            "tag": "psychohistory",
                            "confidence": 0.94,
                            "rationale": "Central predictive science.",
                        },
                        {
                            "tag": "political decline",
                            "confidence": 0.81,
                            "rationale": "The empire is deteriorating.",
                        },
                    ]
                }
            )
        )

        with patch(
            "librarian_metadata.tags.create_configured_generator",
            return_value=generator,
        ):
            result = generate_book_tags(
                GenerateBookTagsOptions(
                    database_url=self.database_url,
                    book_title="Forward the Foundation",
                    author="Isaac Asimov",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )

        with SQLiteIngestionStore(self.database_path) as store:
            stored_tags = store.list_book_tags(book_id="book-1")

        self.assertEqual(result.generated_tags, 2)
        self.assertEqual(result.cached_tags, 0)
        self.assertEqual([tag.tag for tag in result.tags], ["psychohistory", "political decline"])
        self.assertEqual(stored_tags[0].provider, "codex")
        self.assertEqual(stored_tags[0].tag_type, "topic")
        self.assertIn("Do not include genre labels", generator.messages[0].content)

    def test_generate_book_tags_reuses_cached_tags(self) -> None:
        """Verify repeated tag generation can avoid another LLM call.
        Tags are comparatively expensive to regenerate, so cached provider/model
        tags should be returned unless the caller requests a refresh or reset.
        """
        self._seed_book_summary()
        generator = _FakeGenerator(
            json.dumps(
                {
                    "tags": [
                        {
                            "tag": "psychohistory",
                            "confidence": 0.94,
                            "rationale": "Central predictive science.",
                        }
                    ]
                }
            )
        )

        with patch(
            "librarian_metadata.tags.create_configured_generator",
            return_value=generator,
        ):
            generated = generate_book_tags(
                GenerateBookTagsOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )
            cached = generate_book_tags(
                GenerateBookTagsOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    source_summary_provider="codex",
                    source_summary_model="codex",
                )
            )

        self.assertEqual(generated.generated_tags, 1)
        self.assertEqual(cached.generated_tags, 0)
        self.assertEqual(cached.cached_tags, 1)
        self.assertTrue(cached.tags[0].cached)

    def test_generate_book_tags_requires_existing_summary(self) -> None:
        """Verify tag generation fails before calling an LLM without a summary.
        Topic tags are intentionally derived from stored summaries in this pass,
        so missing summary data should produce a clear local error.
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
            generate_book_tags(
                GenerateBookTagsOptions(
                    database_url=self.database_url,
                    book_id="book-1",
                    generation_provider="noop",
                    source_summary_provider="noop",
                    source_summary_model="noop",
                )
            )

    def test_generate_book_tags_rejects_invalid_generator_json(self) -> None:
        """Verify malformed LLM output is rejected before persistence.
        LLM responses are not trusted as-is; the service requires a JSON object
        with a usable tags array.
        """
        self._seed_book_summary()
        generator = _FakeGenerator("not json")

        with patch(
            "librarian_metadata.tags.create_configured_generator",
            return_value=generator,
        ):
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                generate_book_tags(
                    GenerateBookTagsOptions(
                        database_url=self.database_url,
                        book_id="book-1",
                        source_summary_provider="codex",
                        source_summary_model="codex",
                        force_refresh=True,
                    )
                )

        with SQLiteIngestionStore(self.database_path) as store:
            self.assertEqual(store.list_book_tags(book_id="book-1"), [])

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
