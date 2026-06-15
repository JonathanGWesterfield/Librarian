import json
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
INGESTION_PACKAGE = REPO_ROOT / "packages" / "ingestion"
sys.path.insert(0, str(INGESTION_PACKAGE))

from librarian_ingestion.embeddings import NoopEmbedder, OllamaEmbedder, create_embedder


class EmbeddingProviderTests(unittest.TestCase):
    def test_noop_embedder_returns_no_vectors(self) -> None:
        """Verify the default embedder never performs model work.
        Phase 1 ingestion should remain runnable without Ollama, downloaded
        model weights, or any external service.
        """
        embedder = NoopEmbedder()

        self.assertEqual(embedder.embed_texts(["alpha", "beta"]), [])

    def test_create_embedder_selects_ollama_provider(self) -> None:
        """Verify provider selection can construct the Ollama client.
        This protects the config boundary that will let us choose a real local
        model later without changing ingestion orchestration.
        """
        embedder = create_embedder(
            "ollama",
            model="all-minilm",
            ollama_base_url="http://localhost:11434",
        )

        self.assertIsInstance(embedder, OllamaEmbedder)
        self.assertEqual(embedder.model, "all-minilm")

    def test_ollama_embedder_posts_batch_to_embed_endpoint(self) -> None:
        """Verify the Ollama adapter speaks the current embedding API shape.
        Ollama's supported endpoint is `/api/embed`, and it accepts a list of
        input texts so we can batch chunk embeddings efficiently.
        """
        response = _FakeResponse(
            {
                "model": "all-minilm",
                "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            }
        )

        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            vectors = OllamaEmbedder(
                model="all-minilm",
                base_url="http://localhost:11434",
            ).embed_texts(["first", "second"])

        http_request = urlopen.call_args.args[0]
        payload = json.loads(http_request.data.decode("utf-8"))

        self.assertEqual(http_request.full_url, "http://localhost:11434/api/embed")
        self.assertEqual(payload["model"], "all-minilm")
        self.assertEqual(payload["input"], ["first", "second"])
        self.assertEqual(vectors, [[0.1, 0.2], [0.3, 0.4]])


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
