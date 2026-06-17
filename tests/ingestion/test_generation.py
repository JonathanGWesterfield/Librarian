import json
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.generation import (
    ChatMessage,
    NoopGenerator,
    OllamaGenerator,
    create_configured_generator,
    create_generator,
)


class GenerationProviderTests(unittest.TestCase):
    def test_noop_generator_returns_placeholder_answer(self) -> None:
        """Verify generation can be disabled without contacting a model.
        This keeps local tests and dry-run wiring usable before Ollama or model
        weights are installed.
        """
        generator = NoopGenerator()

        self.assertEqual(
            generator.generate([ChatMessage(role="user", content="Hello")]),
            "No generation provider is configured.",
        )

    def test_create_generator_selects_ollama_provider(self) -> None:
        """Verify provider selection can construct the Ollama chat client.
        The chat service should depend on this provider boundary rather than
        hard-coding Ollama request details into orchestration code.
        """
        generator = create_generator(
            "ollama",
            model="llama3.2:3b",
            ollama_base_url="http://localhost:11434",
        )

        self.assertIsInstance(generator, OllamaGenerator)
        self.assertEqual(generator.model, "llama3.2:3b")

    def test_create_configured_generator_resolves_provider_settings(self) -> None:
        """Verify common generation settings resolve through one helper.
        API and CLI callers can pass explicit overrides while environment
        variables remain the fallback for normal local use.
        """
        generator = create_configured_generator(
            provider="ollama",
            model="llama3.2:3b",
            ollama_base_url="http://localhost:11434",
        )

        self.assertIsInstance(generator, OllamaGenerator)
        self.assertEqual(generator.model, "llama3.2:3b")

    def test_ollama_generator_posts_messages_to_chat_endpoint(self) -> None:
        """Verify the Ollama adapter speaks the non-streaming chat API shape.
        Chat answers should use `/api/chat` with messages so future prompt
        changes do not have to alter the transport layer.
        """
        response = _FakeResponse(
            {
                "model": "llama3.2:3b",
                "message": {"role": "assistant", "content": "Grounded answer."},
            }
        )

        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            answer = OllamaGenerator(
                model="llama3.2:3b",
                base_url="http://localhost:11434",
            ).generate(
                [
                    ChatMessage(role="system", content="Use sources."),
                    ChatMessage(role="user", content="Question?"),
                ]
            )

        http_request = urlopen.call_args.args[0]
        payload = json.loads(http_request.data.decode("utf-8"))

        self.assertEqual(http_request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(payload["model"], "llama3.2:3b")
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(answer, "Grounded answer.")


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
