from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from librarian_config import (
    resolve_embedding_model,
    resolve_embedding_provider,
    resolve_ollama_base_url,
)


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    provider: str
    model: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class NoopEmbedder:
    provider: str = "noop"
    model: str = "noop"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return []


@dataclass(frozen=True)
class OllamaEmbedder:
    model: str
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    provider: str = "ollama"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        endpoint = f"{self.base_url.rstrip('/')}/api/embed"
        http_request = request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise EmbeddingError(f"could not reach Ollama at {endpoint}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingError("Ollama returned invalid JSON") from exc

        embeddings = response_payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise EmbeddingError("Ollama response did not include embeddings")
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                "Ollama returned a different number of embeddings than inputs"
            )

        vectors: list[list[float]] = []
        for embedding in embeddings:
            if not isinstance(embedding, list):
                raise EmbeddingError("Ollama returned a non-list embedding")
            vectors.append([float(value) for value in embedding])
        return vectors


def create_embedder(
    provider: str,
    *,
    model: str,
    ollama_base_url: str,
) -> Embedder:
    normalized = provider.strip().casefold()
    if normalized == "noop":
        return NoopEmbedder()
    if normalized == "ollama":
        return OllamaEmbedder(model=model, base_url=ollama_base_url)
    raise ValueError(f"unsupported embedding provider: {provider}")


def create_configured_embedder(
    *,
    provider: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> Embedder:
    resolved_provider = resolve_embedding_provider(provider)
    resolved_model = resolve_embedding_model(model)
    resolved_ollama_base_url = resolve_ollama_base_url(ollama_base_url)
    return create_embedder(
        resolved_provider,
        model=resolved_model,
        ollama_base_url=resolved_ollama_base_url,
    )
