"""Safe endpoint handling for raw OpenAI-compatible gateway clients."""

from __future__ import annotations

from urllib.parse import SplitResult, urlsplit, urlunsplit


class OpenAICompatibleEndpointError(ValueError):
    """Raised when a gateway base URL cannot safely form an API endpoint."""


def build_openai_compatible_endpoint(base_url: str, resource: str) -> str:
    """Build a resource URL after rejecting URL-embedded credentials and tokens."""
    parsed = _validated_base_url(base_url)
    base_path = parsed.path.rstrip("/")
    resource_path = resource.lstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{base_path}/{resource_path}", "", ""))


def validate_openai_compatible_base_url(base_url: str) -> str:
    """Return a normalized safe base URL or raise a secret-safe validation error."""
    parsed = _validated_base_url(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def redacted_openai_compatible_endpoint(value: object) -> str:
    """Return scheme/host/port/path only, never userinfo, query, or fragment data."""
    if not isinstance(value, str):
        return "<invalid configured URL>"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid configured URL>"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "<invalid configured URL>"
    safe_netloc = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    if not safe_netloc:
        return "<invalid configured URL>"
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path or "/", "", ""))


def _validated_base_url(base_url: str) -> SplitResult:
    if not isinstance(base_url, str):
        raise OpenAICompatibleEndpointError(_BASE_URL_REQUIREMENT)
    try:
        parsed = urlsplit(base_url)
    except ValueError as exc:
        raise OpenAICompatibleEndpointError(_BASE_URL_REQUIREMENT) from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OpenAICompatibleEndpointError(_BASE_URL_REQUIREMENT)
    try:
        _ = parsed.port
        has_userinfo = parsed.username is not None or parsed.password is not None
    except ValueError as exc:
        raise OpenAICompatibleEndpointError(_BASE_URL_REQUIREMENT) from exc
    if has_userinfo or parsed.query or parsed.fragment:
        raise OpenAICompatibleEndpointError(_BASE_URL_REQUIREMENT)
    return parsed


_BASE_URL_REQUIREMENT = (
    "OpenAI-compatible base URLs must be http(s) URLs without credentials, "
    "query parameters, or fragments"
)
