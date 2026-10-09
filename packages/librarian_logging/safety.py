"""Safe diagnostics for provider subprocesses and future broker logs.

Request prompts and evidence excerpts are never useful diagnostic fields.  This
module intentionally accepts only provider stderr and removes credential-shaped
content before an operator-facing string is returned.
"""

from __future__ import annotations

import re

MAX_PROVIDER_DIAGNOSTIC_CHARACTERS = 800

_REQUEST_CONTENT_LABEL = re.compile(
    r"(?i)\b(?:prompt|excerpt|message(?:s|[_ -]content)?|evidence(?:[_ -]snapshot)?)\b"
    r"\s*[\"']?\s*[:=]"
)
_BEARER_CREDENTIAL = re.compile(r"(?i)\bbearer\s+[^\s,;\]\}\"']+")
_NAMED_CREDENTIAL = re.compile(
    r"""(?ix)
    \b(?:authorization|api[_ -]?key|token|secret|password|cookie)\b
    \s*[\"']?\s*(?:[:=]|\s)\s*
    (?:[\"']?bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;\]\}]+)
    """
)
_OPENAI_STYLE_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def safe_provider_stderr_diagnostic(
    stderr: str | bytes | None,
    *,
    provider_name: str,
    max_length: int = MAX_PROVIDER_DIAGNOSTIC_CHARACTERS,
) -> str:
    """Return concise stderr that cannot expose known credentials or request text."""

    _validate_provider_name(provider_name)
    _validate_max_length(max_length)
    normalized = _normalize_stderr(stderr)
    if not normalized:
        return (
            f"{provider_name} did not provide stderr; check login, model access, "
            "and provider configuration."
        )
    if _REQUEST_CONTENT_LABEL.search(normalized):
        return f"{provider_name} stderr: [request content redacted]"

    redacted = _NAMED_CREDENTIAL.sub("credential=[redacted]", normalized)
    redacted = _BEARER_CREDENTIAL.sub("Bearer [redacted]", redacted)
    redacted = _OPENAI_STYLE_KEY.sub("sk-[redacted]", redacted)
    if len(redacted) > max_length:
        redacted = f"{redacted[:max_length]} [stderr truncated]"
    return f"{provider_name} stderr: {redacted}"


def _normalize_stderr(stderr: str | bytes | None) -> str:
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    if not isinstance(stderr, str):
        return ""
    return " ".join(stderr.split())


def _validate_provider_name(provider_name: str) -> None:
    if not isinstance(provider_name, str) or not provider_name.strip():
        raise ValueError("provider_name must be a non-empty string")


def _validate_max_length(max_length: int) -> None:
    if not isinstance(max_length, int) or isinstance(max_length, bool) or max_length <= 0:
        raise ValueError("max_length must be a positive integer")
