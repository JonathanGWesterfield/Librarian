from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib import error, request

from librarian_config.config import (
    resolve_codex_executable,
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


@dataclass(frozen=True)
class CodexGenerator:
    model: str = "codex"
    executable: str = "codex"
    timeout_seconds: float = 240.0
    provider: str = "codex"

    def generate(self, messages: list[ChatMessage]) -> str:
        prompt = "\n\n".join(
            f"{message.role.upper()}:\n{message.content}" for message in messages
        )
        executable = _resolve_codex_command(self.executable)
        try:
            completed = subprocess.run(
                [
                    executable,
                    "exec",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--sandbox",
                    "read-only",
                    "-",
                ],
                check=True,
                capture_output=True,
                input=prompt,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise GenerationError(
                "Codex executable was not found. Install the Codex CLI or set "
                "LIBRARIAN_CODEX_EXECUTABLE to the full path returned by "
                "`which codex`."
            ) from exc
        except OSError as exc:
            raise GenerationError(f"Codex generation failed: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise GenerationError(
                f"Codex generation timed out after {self.timeout_seconds:.0f} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = _trim_error_output(exc.stderr or "")
            detail = f": {stderr}" if stderr else ""
            raise GenerationError(
                f"Codex generation failed with exit code {exc.returncode}{detail}"
            ) from exc
        return completed.stdout.strip()


def create_generator(
    provider: str,
    *,
    model: str,
    ollama_base_url: str | None = None,
) -> Generator:
    normalized = provider.strip().casefold()
    if normalized == "noop":
        return NoopGenerator()
    if normalized == "ollama":
        return OllamaGenerator(
            model=model,
            base_url=resolve_ollama_base_url(ollama_base_url),
        )
    if normalized == "codex":
        return CodexGenerator(
            model=model or "codex",
            executable=resolve_codex_executable(),
        )
    raise ValueError(f"unsupported generation provider: {provider}")


def create_configured_generator(
    *,
    provider: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> Generator:
    resolved_provider = resolve_generation_provider(provider)
    if resolved_provider.strip().casefold() == "codex" and model is None:
        resolved_model = "codex"
    else:
        resolved_model = resolve_generation_model(model)
    return create_generator(
        resolved_provider,
        model=resolved_model,
        ollama_base_url=ollama_base_url,
    )


def _resolve_codex_command(configured: str) -> str:
    if Path(configured).expanduser().exists():
        return str(Path(configured).expanduser())

    discovered = shutil.which(configured)
    if discovered:
        return discovered

    home = Path.home()
    for candidate in home.glob(
        ".vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex"
    ):
        if candidate.exists():
            return str(candidate)

    return configured


def _trim_error_output(output: str, max_length: int = 1200) -> str:
    cleaned = output.strip()
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[-max_length:]}\n[stderr truncated]"
