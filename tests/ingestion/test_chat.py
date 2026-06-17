import sys
import unittest
from unittest.mock import patch

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_chat.chat import ChatOptions, answer_question
from librarian_search.search import SearchResponse, SearchResult


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

        with patch("librarian_chat.chat.search_chunks", return_value=fake_search):
            with patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ):
                response = answer_question(
                    ChatOptions(
                        question=" How brutal is war? ",
                        database_url="sqlite:///tmp/librarian.db",
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="llama3.2:3b",
                        retrieval_limit=20,
                    )
                )

        self.assertEqual(response.question, "How brutal is war?")
        self.assertEqual(response.answer, "War is described as terrifying. [S1]")
        self.assertEqual(response.candidate_count, 2)
        self.assertEqual(response.sources[0].source_id, "S1")
        self.assertEqual(response.sources[0].title, "All Quiet on the Western Front")
        prompt = generator.messages[-1].content
        self.assertIn("[S1]", prompt)
        self.assertIn("The front is a cage", prompt)


class _FakeGenerator:
    provider = "ollama"
    model = "llama3.2:3b"

    def __init__(self) -> None:
        self.messages = []

    def generate(self, messages):
        self.messages = messages
        return "War is described as terrifying. [S1]"


if __name__ == "__main__":
    unittest.main()
