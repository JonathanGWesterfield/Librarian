from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol
from urllib import error, request

from librarian_config.config import (
    resolve_embedding_model,
    resolve_embedding_ollama_base_url,
    resolve_embedding_openai_compatible,
    resolve_embedding_provider,
)
from librarian_config.openai_compatible import build_openai_compatible_endpoint


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


@dataclass(frozen=True)
class OpenAICompatibleEmbedder:
    """Embedding client for a configured OpenAI-compatible gateway."""

    model: str
    base_url: str
    api_key: str
    extra_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 120.0
    provider: str = "openai_compatible"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        headers.update(self.extra_headers)
        endpoint = build_openai_compatible_endpoint(self.base_url, "embeddings")
        http_request = request.Request(
            endpoint,
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise EmbeddingError(f"OpenAI-compatible embedding gateway returned HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise EmbeddingError("could not reach OpenAI-compatible embedding gateway") from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingError("OpenAI-compatible gateway returned invalid JSON") from exc
        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list) or len(records) != len(texts):
            raise EmbeddingError("OpenAI-compatible gateway returned an invalid embeddings response")
        vectors: list[list[float]] = []
        for record in records:
            vector = record.get("embedding") if isinstance(record, dict) else None
            if not isinstance(vector, list):
                raise EmbeddingError("OpenAI-compatible gateway returned a non-list embedding")
            vectors.append([float(value) for value in vector])
        return vectors


def create_embedder(
    provider: str,
    *,
    model: str,
    ollama_base_url: str | None = None,
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    openai_headers: dict[str, str] | None = None,
) -> Embedder:
    normalized = provider.strip().casefold()
    if normalized == "noop":
        return NoopEmbedder()
    if normalized == "ollama":
        if not ollama_base_url:
            raise ValueError("Ollama embedding provider requires an Ollama base URL")
        return OllamaEmbedder(model=model, base_url=ollama_base_url)
    if normalized == "openai_compatible":
        if not openai_base_url or not openai_api_key:
            raise ValueError(
                "OpenAI-compatible embedding provider requires base_url and api_key_file in librarian.json"
            )
        return OpenAICompatibleEmbedder(
            model=model,
            base_url=openai_base_url,
            api_key=openai_api_key,
            extra_headers=openai_headers or {},
        )
    raise ValueError(f"unsupported embedding provider: {provider}")


def create_configured_embedder(
    *,
    provider: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> Embedder:
    resolved_provider = resolve_embedding_provider(provider)
    resolved_model = resolve_embedding_model(model)
    normalized = resolved_provider.strip().casefold()
    if normalized == "noop":
        return create_embedder(resolved_provider, model=resolved_model)
    if normalized == "ollama":
        return create_embedder(
            resolved_provider,
            model=resolved_model,
            ollama_base_url=resolve_embedding_ollama_base_url(ollama_base_url),
        )
    if normalized == "openai_compatible":
        base_url, api_key, headers = resolve_embedding_openai_compatible()
        return create_embedder(
            resolved_provider,
            model=resolved_model,
            openai_base_url=base_url,
            openai_api_key=api_key,
            openai_headers=headers,
        )
    return create_embedder(
        resolved_provider,
        model=resolved_model,
    )
