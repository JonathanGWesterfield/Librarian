import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.chat import ChatOptions, answer_question
from librarian_ingestion.embedding_ops import EmbedQueryResult
from librarian_search.opensearch import OpenSearchError
from librarian_search.search import SearchResponse, SearchResult
from librarian_storage.storage import BookRecord, SQLiteIngestionStore, utc_now


class ChatTests(unittest.TestCase):
    def test_answer_question_retrieves_sources_and_generates_answer(self) -> None:
        """Verify chat composes retrieval and local generation.
        This protects the end-to-end service boundary: search supplies ranked
        chunks, the prompt includes source IDs, and the response preserves
        source metadata for citations.
        """
        fake_search = SearchResponse(
            query="How brutal is war?",
            embedding_provider="ollama",
            embedding_model="all-minilm",
            dimensions=2,
            candidate_count=2,
            filters={"author": "Erich Maria Remarque"},
            results=[
                SearchResult(
                    score=0.9,
                    chunk_id="book:0",
                    book_id="book",
                    relative_path="All Quiet.epub",
                    title="All Quiet on the Western Front",
                    authors=["Erich Maria Remarque"],
                    publisher=None,
                    chunk_index=0,
                    text="The front is a cage in which we must await fearfully.",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    dimensions=2,
                )
            ],
        )
        generator = _FakeGenerator()

        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch("librarian_chat.chat.search_chunks", return_value=fake_search),
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question=" How brutal is war? ",
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    answer_capability="quality",
                    retrieval_limit=20,
                    author="Erich Maria Remarque",
                )
            )

        self.assertEqual(response.question, "How brutal is war?")
        self.assertEqual(response.answer, "War is described as terrifying. [S1]")
        self.assertEqual(response.answer_capability, "quality")
        self.assertEqual(response.filters, {"author": "Erich Maria Remarque"})
        self.assertEqual(response.candidate_count, 2)
        self.assertEqual(response.retrieval_backend, "sqlite")
        self.assertEqual(response.sources[0].source_id, "S1")
        self.assertEqual(response.sources[0].title, "All Quiet on the Western Front")
        self.assertGreaterEqual(response.timings.query_embedding_seconds, 0.0)
        self.assertGreaterEqual(response.timings.retrieval_seconds, 0.0)
        self.assertGreaterEqual(response.timings.prompt_construction_seconds, 0.0)
        self.assertGreaterEqual(response.timings.generation_seconds, 0.0)
        self.assertGreaterEqual(response.timings.total_seconds, 0.0)
        prompt = generator.messages[-1].content
        self.assertIn("[S1]", prompt)
        self.assertIn("The front is a cage", prompt)

    def test_answer_question_uses_opensearch_hybrid_when_auto_backend_is_healthy(self) -> None:
        """Auto chat retrieval should use the indexed hybrid path and keep scope."""
        generator = _FakeGenerator()
        fake_search = _search_response()

        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="auto"),
            patch(
                "librarian_chat.chat.hybrid_search_chunks", return_value=fake_search
            ) as hybrid_search,
            patch("librarian_chat.chat.search_chunks") as sqlite_search,
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question="How brutal is war?",
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    answer_capability="quality",
                    retrieval_limit=20,
                    book_title="All Quiet",
                    author="Erich Maria Remarque",
                )
            )

        self.assertEqual(response.retrieval_backend, "opensearch")
        sqlite_search.assert_not_called()
        hybrid_options = hybrid_search.call_args.args[0]
        self.assertEqual(hybrid_options.query_embedding, _query_embedding())
        self.assertEqual(hybrid_options.book_title, "All Quiet")
        self.assertEqual(hybrid_options.author, "Erich Maria Remarque")
        self.assertEqual(hybrid_options.limit, 20)
        self.assertEqual(response.sources[0].to_dict(), {
            "source_id": "S1",
            "score": 0.9,
            "chunk_id": "book:0",
            "book_id": "book",
            "relative_path": "All Quiet.epub",
            "title": "All Quiet on the Western Front",
            "authors": ["Erich Maria Remarque"],
            "chunk_index": 0,
            "content_type": "body",
            "text": "The front is a cage in which we must await fearfully.",
        })
        self.assertEqual(set(response.timings.to_dict()), {
            "query_embedding_seconds",
            "retrieval_seconds",
            "prompt_construction_seconds",
            "generation_seconds",
            "total_seconds",
        })

    def test_answer_question_falls_back_to_sqlite_when_auto_opensearch_is_unavailable(self) -> None:
        """An unavailable projection must not stop source-of-truth chat retrieval."""
        generator = _FakeGenerator()
        fake_search = _search_response()

        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="auto"),
            patch(
                "librarian_chat.chat.hybrid_search_chunks",
                side_effect=OpenSearchError("index is unavailable"),
            ),
            patch(
                "librarian_chat.chat.search_chunks", return_value=fake_search
            ) as sqlite_search,
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question="How brutal is war?",
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    answer_capability="quality",
                    retrieval_limit=20,
                    book_id="book",
                )
            )

        self.assertEqual(response.retrieval_backend, "sqlite")
        sqlite_options = sqlite_search.call_args.args[0]
        self.assertEqual(sqlite_options.query_embedding, _query_embedding())
        self.assertEqual(sqlite_options.book_id, "book")
        self.assertEqual(response.sources[0].source_id, "S1")

    def test_author_view_question_auto_scopes_the_unique_named_author_for_spelled_and_misspelled_terms(self) -> None:
        """Whole-library author questions must not leak evidence from other writers."""
        with TemporaryDirectory() as temp_dir:
            database_url = _seed_author_scope_database(Path(temp_dir) / "librarian.db")
            for question in (
                "What does C.S. Lewis say about modern Christianity?",
                "What does C.S. Lewis say about modern Chrisitanity?",
            ):
                generator = _FakeGenerator()
                fake_search = _author_search_response(question, count=10)
                with (
                    patch(
                        "librarian_chat.chat.embed_query",
                        return_value=_query_embedding_for(question),
                    ),
                    patch(
                        "librarian_chat.chat.resolve_chat_retrieval_backend",
                        return_value="opensearch",
                    ),
                    patch(
                        "librarian_chat.chat.hybrid_search_chunks",
                        return_value=fake_search,
                    ) as hybrid_search,
                    patch(
                        "librarian_chat.chat.create_configured_generator",
                        return_value=generator,
                    ),
                ):
                    response = answer_question(
                        ChatOptions(
                            question=question,
                            database_url=database_url,
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )

                self.assertEqual(response.retrieval_backend, "opensearch")
                self.assertEqual(hybrid_search.call_args.args[0].author, "C. S. Lewis")
                self.assertEqual(hybrid_search.call_args.args[0].query, question)
                self.assertNotIn("Other Author", generator.messages[-1].content)
                self.assertIn("at least 10 distinct source IDs", generator.messages[-1].content)

    def test_broad_author_question_with_only_one_body_source_does_not_generate(self) -> None:
        """A single weak passage must never be turned into a model-prior synthesis."""
        question = "What does C.S. Lewis say about modern Christianity?"
        with TemporaryDirectory() as temp_dir:
            database_url = _seed_author_scope_database(Path(temp_dir) / "librarian.db")
            generator = _FakeGenerator()
            with (
                patch(
                    "librarian_chat.chat.embed_query",
                    return_value=_query_embedding_for(question),
                ),
                patch(
                    "librarian_chat.chat.resolve_chat_retrieval_backend",
                    return_value="sqlite",
                ),
                patch(
                    "librarian_chat.chat.search_chunks",
                    return_value=_author_search_response(question, count=1),
                ),
                patch(
                    "librarian_chat.chat.create_configured_generator",
                    return_value=generator,
                ),
            ):
                response = answer_question(
                    ChatOptions(
                        question=question,
                        database_url=database_url,
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:7b",
                        answer_capability="quality",
                    )
                )

        self.assertIn("enough distinct body-text passages", response.answer)
        self.assertEqual(generator.messages, [])

    def test_lightweight_lookup_is_extractive_for_scoped_and_unscoped_gate_questions(self) -> None:
        """A lightweight lookup must preserve Mara as the source sentence subject."""
        question = "Who opens the garden gate?"
        search_response = _chat_search_response(
            question,
            text=(
                "The clockwork garden woke at dawn.\n"
                "A brass robin counted three silver seeds.\n"
                "Mara opened the gate with a borrowed key."
            ),
        )
        for book_title in (None, "The Clockwork Garden"):
            generator = _FakeGenerator()
            with (
                patch(
                    "librarian_chat.chat.embed_query",
                    return_value=_query_embedding_for(question),
                ),
                patch(
                    "librarian_chat.chat.resolve_chat_retrieval_backend",
                    return_value="sqlite",
                ),
                patch(
                    "librarian_chat.chat.search_chunks", return_value=search_response
                ) as search_chunks,
                patch(
                    "librarian_chat.chat.create_configured_generator",
                    return_value=generator,
                ),
            ):
                response = answer_question(
                    ChatOptions(
                        question=question,
                        database_url="sqlite:///tmp/librarian.db",
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:1.5b",
                        answer_capability="lightweight",
                        book_title=book_title,
                    )
                )

            self.assertEqual(response.answer, "Mara opened the gate with a borrowed key. [S1]")
            self.assertEqual(search_chunks.call_args.args[0].book_title, book_title)
            self.assertEqual(generator.messages, [])

    def test_lightweight_lookup_refuses_when_no_source_sentence_supports_the_question(self) -> None:
        """Never fall through to a small model after extractive support fails."""
        question = "Who opens the garden gate?"
        generator = _FakeGenerator()
        with (
            patch(
                "librarian_chat.chat.embed_query",
                return_value=_query_embedding_for(question),
            ),
            patch(
                "librarian_chat.chat.resolve_chat_retrieval_backend",
                return_value="sqlite",
            ),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="A brass robin counted three silver seeds.",
                ),
            ),
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:1.5b",
                    answer_capability="lightweight",
                )
            )

        self.assertIn("enough relevant body-text evidence", response.answer)
        self.assertEqual(generator.messages, [])

    def test_publication_question_requires_non_body_publisher_evidence(self) -> None:
        """Body prose cannot become a citation for a publisher question."""
        question = "Who published The Clockwork Garden?"
        body_only = _chat_search_response(
            question,
            text="The clockwork garden woke at dawn.",
        )
        front_matter = _chat_search_response(
            question,
            text="Published by Fixture Press in 2024.",
            content_type="front_matter",
        )
        for search_response, expected_answer in (
            (
                body_only,
                "I could not find publication or edition evidence in the local EPUB content to answer that reliably.",
            ),
            (front_matter, "Published by Fixture Press in 2024. [S1]"),
        ):
            generator = _FakeGenerator()
            with (
                patch(
                    "librarian_chat.chat.embed_query",
                    return_value=_query_embedding_for(question),
                ),
                patch(
                    "librarian_chat.chat.resolve_chat_retrieval_backend",
                    return_value="sqlite",
                ),
                patch(
                    "librarian_chat.chat.search_chunks", return_value=search_response
                ) as search_chunks,
                patch(
                    "librarian_chat.chat.create_configured_generator",
                    return_value=generator,
                ),
            ):
                response = answer_question(
                    ChatOptions(
                        question=question,
                        database_url="sqlite:///tmp/librarian.db",
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:1.5b",
                        answer_capability="lightweight",
                    )
                )

            self.assertEqual(response.answer, expected_answer)
            self.assertTrue(search_chunks.call_args.args[0].include_non_content)
            self.assertEqual(generator.messages, [])
        self.assertEqual(body_only.results[0].content_type, "body")


def _query_embedding() -> EmbedQueryResult:
    return EmbedQueryResult(
        query="How brutal is war?",
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        vector=[1.0, 0.0],
    )


def _query_embedding_for(question: str) -> EmbedQueryResult:
    return EmbedQueryResult(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        vector=[1.0, 0.0],
    )


def _seed_author_scope_database(database_path: Path) -> str:
    with SQLiteIngestionStore(database_path) as store:
        for book_id, author in (("lewis", "C. S. Lewis"), ("other", "Other Author")):
            store.save_book_with_chunks(
                BookRecord(
                    id=book_id,
                    source_path=f"/books/{book_id}.epub",
                    relative_path=f"{book_id}.epub",
                    file_hash=book_id,
                    size_bytes=100,
                    title=f"{author} Book",
                    authors=[author],
                    status="ingested",
                    ingested_at=utc_now(),
                ),
                [],
            )
    return f"sqlite:///{database_path}"


def _author_search_response(question: str, *, count: int) -> SearchResponse:
    return SearchResponse(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=count,
        filters={"author": "C. S. Lewis"},
        results=[
            SearchResult(
                score=0.9 - (index / 100),
                chunk_id=f"lewis:{index}",
                book_id="lewis",
                relative_path="screwtape.epub",
                title="The Screwtape Letters",
                authors=["C. S. Lewis"],
                publisher=None,
                chunk_index=index,
                text=(
                    "Lewis examines modern Christianity through ordinary moral choices "
                    "and self-deception."
                ),
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
            for index in range(count)
        ],
    )


def _chat_search_response(
    question: str,
    *,
    text: str,
    content_type: str = "body",
) -> SearchResponse:
    return SearchResponse(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=1,
        filters={},
        results=[
            SearchResult(
                score=0.9,
                chunk_id="clockwork:0",
                book_id="clockwork",
                relative_path="clockwork.epub",
                title="The Clockwork Garden",
                authors=["Test Author"],
                publisher="Fixture Press",
                chunk_index=0,
                content_type=content_type,
                text=text,
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
        ],
    )


def _search_response() -> SearchResponse:
    return SearchResponse(
        query="How brutal is war?",
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=2,
        filters={"author": "Erich Maria Remarque"},
        results=[
            SearchResult(
                score=0.9,
                chunk_id="book:0",
                book_id="book",
                relative_path="All Quiet.epub",
                title="All Quiet on the Western Front",
                authors=["Erich Maria Remarque"],
                publisher=None,
                chunk_index=0,
                text="The front is a cage in which we must await fearfully.",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
        ],
    )


class _FakeGenerator:
    provider = "ollama"
    model = "llama3.2:3b"

    def __init__(self) -> None:
        self.messages = []

    def generate(self, messages, *, response_format=None):
        self.messages = messages
        return "War is described as terrifying. [S1]"


if __name__ == "__main__":
    unittest.main()
