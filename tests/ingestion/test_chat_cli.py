import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from chat import main
from librarian_chat.chat import ChatResponse, ChatSource


class ChatCliTests(unittest.TestCase):
    def test_chat_cli_prints_answer_and_sources(self) -> None:
        """Verify the standalone chat CLI can replace a frontend for now.
        The script should accept a one-shot question and show the generated
        answer plus source IDs for quick local experimentation.
        """
        fake_response = ChatResponse(
            question="How brutal is war?",
            answer="War is terrifying and dehumanizing. [S1]",
            embedding_provider="ollama",
            embedding_model="all-minilm",
            generation_provider="ollama",
            generation_model="llama3.2:3b",
            retrieval_limit=20,
            candidate_count=1,
            filters={},
            sources=[
                ChatSource(
                    source_id="S1",
                    score=0.9,
                    chunk_id="book:0",
                    book_id="book",
                    relative_path="All Quiet.epub",
                    title="All Quiet on the Western Front",
                    authors=["Erich Maria Remarque"],
                    chunk_index=0,
                    text="The front is terrifying.",
                )
            ],
        )

        with patch("chat.answer_question", return_value=fake_response):
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["How brutal is war?", "--retrieval-limit", "20"])

        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        self.assertIn("War is terrifying", rendered)
        self.assertIn("[S1]", rendered)
        self.assertIn("All Quiet on the Western Front", rendered)

    def test_chat_cli_forwards_an_explicit_generation_capability(self) -> None:
        """Verify the CLI can select a one-off model without model-name guessing."""
        fake_response = ChatResponse(
            question="What does the author say?",
            answer="A grounded answer.",
            embedding_provider="ollama",
            embedding_model="all-minilm",
            generation_provider="ollama",
            generation_model="qwen2.5:7b",
            retrieval_limit=30,
            candidate_count=1,
            filters={},
            sources=[],
            answer_capability="quality",
        )

        with patch("chat.answer_question", return_value=fake_response) as answer:
            exit_code = main(
                [
                    "--generation-provider",
                    "ollama",
                    "--generation-model",
                    "qwen2.5:7b",
                    "--answer-capability",
                    "quality",
                    "What does the author say?",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(answer.call_args.args[0].answer_capability, "quality")


if __name__ == "__main__":
    unittest.main()
