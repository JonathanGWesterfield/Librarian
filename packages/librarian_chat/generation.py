from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
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

logger = logging.getLogger(__name__)


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class Generator(Protocol):
    provider: str
    model: str

    def generate(
        self, messages: list[ChatMessage], *, response_format: str | None = None
    ) -> str:
        ...


@dataclass(frozen=True)
class NoopGenerator:
    provider: str = "noop"
    model: str = "noop"

    def generate(
        self, messages: list[ChatMessage], *, response_format: str | None = None
    ) -> str:
        return "No generation provider is configured."


@dataclass(frozen=True)
class OllamaGenerator:
    model: str
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 180.0
    provider: str = "ollama"

    def generate(
        self, messages: list[ChatMessage], *, response_format: str | None = None
    ) -> str:
        payload_dict: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "stream": False,
        }
        if response_format == "json":
            payload_dict["format"] = "json"
        payload = json.dumps(
            payload_dict
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
    progress_interval_seconds: float = 30.0
    provider: str = "codex"

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        response_format: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        prompt = "\n\n".join(
            f"{message.role.upper()}:\n{message.content}" for message in messages
        )
        executable = _resolve_codex_command(self.executable)
        command = [
            executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "-",
        ]
        effective_timeout_seconds = (
            self.timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        try:
            completed = _run_codex_process(
                command,
                prompt=prompt,
                timeout_seconds=effective_timeout_seconds,
                progress_interval_seconds=self.progress_interval_seconds,
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
                f"Codex generation timed out after {effective_timeout_seconds:.0f} seconds"
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


@dataclass(frozen=True)
class _CodexProcessResult:
    stdout: str
    stderr: str


def _run_codex_process(
    command: list[str],
    *,
    prompt: str,
    timeout_seconds: float,
    progress_interval_seconds: float,
) -> _CodexProcessResult:
    logger.info(
        "Starting Codex subprocess with timeout %.0fs: %s",
        timeout_seconds,
        _redacted_command(command),
    )
    started_at = time.monotonic()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if process.stdin is not None:
        process.stdin.write(prompt)
        process.stdin.close()

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    threads = [
        threading.Thread(
            target=_capture_process_stream,
            args=(process.stdout, "stdout", stdout_lines),
            daemon=True,
        ),
        threading.Thread(
            target=_capture_process_stream,
            args=(process.stderr, "stderr", stderr_lines),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    next_progress_at = started_at + max(1.0, progress_interval_seconds)
    deadline = started_at + timeout_seconds
    while True:
        returncode = process.poll()
        if returncode is not None:
            break

        now = time.monotonic()
        if now >= deadline:
            process.kill()
            process.wait()
            _join_stream_threads(threads)
            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)
            raise subprocess.TimeoutExpired(
                command,
                timeout_seconds,
                output=stdout,
                stderr=stderr,
            )

        if now >= next_progress_at:
            logger.info(
                "Codex subprocess still running after %.0fs",
                now - started_at,
            )
            next_progress_at = now + max(1.0, progress_interval_seconds)

        time.sleep(min(0.25, max(0.0, deadline - now)))

    _join_stream_threads(threads)
    elapsed_seconds = time.monotonic() - started_at
    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)
    if returncode != 0:
        raise subprocess.CalledProcessError(
            returncode,
            command,
            output=stdout,
            stderr=stderr,
        )

    logger.info("Codex subprocess completed in %.1fs", elapsed_seconds)
    return _CodexProcessResult(stdout=stdout, stderr=stderr)


def _capture_process_stream(stream, name: str, output: list[str]) -> None:
    if stream is None:
        return
    try:
        for line in iter(stream.readline, ""):
            output.append(line)
            cleaned = line.rstrip()
            if cleaned:
                logger.info("Codex %s: %s", name, cleaned)
    finally:
        stream.close()


def _join_stream_threads(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=1.0)


def _redacted_command(command: list[str]) -> str:
    return " ".join(command)


def _trim_error_output(output: str, max_length: int = 1200) -> str:
    cleaned = output.strip()
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[-max_length:]}\n[stderr truncated]"
