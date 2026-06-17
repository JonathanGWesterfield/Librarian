from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from librarian_config.config import (
    resolve_generation_model,
    resolve_generation_provider,
    resolve_ollama_base_url,
)


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class Generator(Protocol):
    provider: str
    model: str

    def generate(self, messages: list[ChatMessage]) -> str:
        ...


@dataclass(frozen=True)
class NoopGenerator:
    provider: str = "noop"
    model: str = "noop"

    def generate(self, messages: list[ChatMessage]) -> str:
        return "No generation provider is configured."


@dataclass(frozen=True)
class OllamaGenerator:
    model: str
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 180.0
    provider: str = "ollama"

    def generate(self, messages: list[ChatMessage]) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
                "stream": False,
            }
        ).encode("utf-8")
        endpoint = f"{self.base_url.rstrip('/')}/api/chat"
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
            raise GenerationError(f"could not reach Ollama at {endpoint}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise GenerationError("Ollama returned invalid JSON") from exc

        message = response_payload.get("message")
        if not isinstance(message, dict):
            raise GenerationError("Ollama response did not include a message")

        content = message.get("content")
        if not isinstance(content, str):
            raise GenerationError("Ollama response message did not include content")
        return content.strip()


def create_generator(
    provider: str,
    *,
    model: str,
    ollama_base_url: str,
) -> Generator:
    normalized = provider.strip().casefold()
    if normalized == "noop":
        return NoopGenerator()
    if normalized == "ollama":
        return OllamaGenerator(model=model, base_url=ollama_base_url)
    raise ValueError(f"unsupported generation provider: {provider}")


def create_configured_generator(
    *,
    provider: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> Generator:
    resolved_provider = resolve_generation_provider(provider)
    resolved_model = resolve_generation_model(model)
    resolved_ollama_base_url = resolve_ollama_base_url(ollama_base_url)
    return create_generator(
        resolved_provider,
        model=resolved_model,
        ollama_base_url=resolved_ollama_base_url,
    )
