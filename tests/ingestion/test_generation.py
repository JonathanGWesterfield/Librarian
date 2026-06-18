import json
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.generation import (
    ChatMessage,
    CodexGenerator,
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

    def test_create_generator_selects_codex_provider(self) -> None:
        """Verify provider selection can construct the Codex CLI adapter.
        Summarization will use the same generation boundary as chat, so Codex
        needs to be selectable without changing orchestration code.
        """
        generator = create_generator(
            "codex",
            model="codex",
            ollama_base_url="http://localhost:11434",
        )

        self.assertIsInstance(generator, CodexGenerator)
        self.assertEqual(generator.model, "codex")

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

    def test_create_configured_generator_defaults_codex_model(self) -> None:
        """Verify Codex does not inherit the local Ollama default model name.
        This keeps provider/model metadata honest for summary rebuilds and
        comparisons when callers only pass `--generation-provider codex`.
        """
        generator = create_configured_generator(provider="codex")

        self.assertIsInstance(generator, CodexGenerator)
        self.assertEqual(generator.model, "codex")

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

    def test_codex_generator_runs_codex_exec_with_prompt(self) -> None:
        """Verify the Codex adapter shells out through `codex exec`.
        The adapter keeps CLI usage behind the generator protocol so callers
        can swap between Ollama and Codex with provider settings.
        """
        completed = __import__("subprocess").CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout="Codex answer.\n",
            stderr="",
        )

        with patch("subprocess.run", return_value=completed) as run:
            answer = CodexGenerator().generate(
                [
                    ChatMessage(role="system", content="Summarize."),
                    ChatMessage(role="user", content="Text."),
                ]
            )

        self.assertEqual(answer, "Codex answer.")
        self.assertTrue(run.call_args.args[0][0].endswith("codex"))
        self.assertEqual(
            run.call_args.args[0][1:],
            [
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--sandbox",
                "read-only",
                "-",
            ],
        )
        self.assertIn("SYSTEM:\nSummarize.", run.call_args.kwargs["input"])
        self.assertEqual(run.call_args.kwargs["timeout"], 240.0)

    def test_codex_generator_reports_missing_executable_clearly(self) -> None:
        """Verify missing Codex CLI setup produces an actionable message.
        A local terminal may not have the same PATH as the Codex extension, so
        this error should point users at the explicit executable setting.
        """
        with patch("shutil.which", return_value=None):
            with patch("pathlib.Path.exists", return_value=False):
                with patch("subprocess.run", side_effect=FileNotFoundError):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "LIBRARIAN_CODEX_EXECUTABLE",
                    ):
                        CodexGenerator(executable="missing-codex").generate(
                            [ChatMessage(role="user", content="Hello")]
                        )

    def test_codex_generator_trims_large_stderr(self) -> None:
        """Verify noisy Codex CLI failures stay readable.
        Network failures can emit pages of retry logs, but callers only need a
        concise error that preserves the useful tail.
        """
        error = __import__("subprocess").CalledProcessError(
            returncode=1,
            cmd=["codex"],
            stderr="x" * 2000,
        )

        with patch("subprocess.run", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "stderr truncated"):
                CodexGenerator(executable="codex").generate(
                    [ChatMessage(role="user", content="Hello")]
                )


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
