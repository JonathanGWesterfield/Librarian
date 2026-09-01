"""Internal, OpenAI-compatible broker for a Docker-resident Codex CLI.

The broker is intentionally reachable only on the Compose network. Its Codex
login/session is kept in the ``codex-broker-session`` named volume; the host's
``~/.codex`` directory is never mounted into this service.
"""

from __future__ import annotations

import hmac
import subprocess
import time
import uuid
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, Header, HTTPException, status
from librarian_config.config import LibrarianConfigError, get_librarian_config
from librarian_logging import configure_logging
from pydantic import BaseModel, Field

configure_logging()

app = FastAPI(title="Librarian Codex Broker", version="0.2.0")


class OpenAIMessage(BaseModel):
    """The deliberately small chat-message subset used by Librarian."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionRequest(BaseModel):
    """Non-streaming OpenAI-compatible request forwarded to ``codex exec``."""

    model: str = Field(min_length=1)
    messages: list[OpenAIMessage] = Field(min_length=1)
    stream: bool = False
    response_format: Optional[Dict[str, str]] = None
    temperature: Optional[float] = None


class ChatCompletionResponse(BaseModel):
    """Minimal response shape consumed by ``OpenAICompatibleGenerator``."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, object]]


@app.get("/health")
def health() -> dict[str, str]:
    """Confirm that the broker process is alive; login is verified at request time."""
    return {"status": "ok"}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(default=None),
) -> ChatCompletionResponse:
    """Run the configured Codex model after authenticating the internal caller."""
    config = _configured_broker()
    _require_bearer_token(authorization, config.generation.api_key)
    if request.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Docker Codex broker supports non-streaming chat completions only.",
        )
    if request.model.strip() != config.generation.model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Docker Codex broker only accepts the model configured in librarian.json.",
        )

    try:
        completed = subprocess.run(
            [
                "codex",
                "exec",
                "--model",
                config.generation.model,
                "--ephemeral",
                "--sandbox",
                "read-only",
                "-",
            ],
            input=_build_prompt(request.messages),
            check=True,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Codex CLI is unavailable in the broker image.",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The configured Codex model did not respond within 240 seconds.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Codex CLI exited with code {exc.returncode}. Verify the broker login with "
                "`docker compose --profile codex-broker run --rm codex-broker codex login`."
            ),
        ) from exc

    answer = completed.stdout.strip()
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Codex CLI returned an empty response.",
        )
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=config.generation.model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
    )


def _configured_broker():
    """Load only the explicit Compose-native broker configuration."""
    try:
        config = get_librarian_config()
    except LibrarianConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The broker could not load the Librarian JSON configuration.",
        ) from exc
    if not config.generation.uses_docker_codex_broker or not config.generation.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The broker requires generation.mode to be docker_codex_broker.",
        )
    return config


def _require_bearer_token(authorization: str | None, expected_token: str | None) -> None:
    """Authenticate only the API/worker caller without exposing a public port."""
    scheme, separator, token = (authorization or "").partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not expected_token
        or not hmac.compare_digest(token, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid internal broker bearer token is required.",
        )


def _build_prompt(messages: list[OpenAIMessage]) -> str:
    """Preserve structured roles without giving request data shell authority."""
    return "\n\n".join(
        f"{message.role.upper()}:\n{message.content}" for message in messages
    )
