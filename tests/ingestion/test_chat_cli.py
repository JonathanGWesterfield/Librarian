import sys
import unittest
from contextlib import redirect_stderr
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
            with redirect_stderr(output):
                exit_code = main(["How brutal is war?", "--retrieval-limit", "20"])

        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        self.assertIn("War is terrifying", rendered)
        self.assertIn("[S1]", rendered)
        self.assertIn("All Quiet on the Western Front", rendered)


if __name__ == "__main__":
    unittest.main()
