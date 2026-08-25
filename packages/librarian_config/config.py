"""Load and validate Librarian's user-owned JSON configuration.

Librarian deliberately does not read legacy configuration environment variables.
Copy ``config/librarian.example.json`` to the ignored
``config/librarian.json`` file, then make all operational changes there.
External provider credentials are read from files relative to that JSON file;
they are never copied to process environment variables.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from librarian_config.openai_compatible import (
    OpenAICompatibleEndpointError,
    validate_openai_compatible_base_url,
)

CONFIG_FILENAME = "librarian.json"
CONFIG_DIRECTORY_NAME = "config"
CONTAINER_CONFIG_PATH = Path("/config") / CONFIG_FILENAME
_ALLOWED_PROVIDER_MODES = {
    "docker_ollama",
    "native_ollama",
    "openai_compatible",
    "codex",
}
_ALLOWED_ANSWER_CAPABILITIES = {"quality", "lightweight"}
_HTTP_HEADER_NAME = frozenset(
    "!#$%&'*+.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-"
)


class LibrarianConfigError(ValueError):
    """Raised when the required Librarian JSON configuration is unsafe or invalid."""


@dataclass(frozen=True)
class PathSettings:
    books_dir: str
    host_books_dir: str
    database_url: str
    log_file: str


@dataclass(frozen=True)
class ProviderSettings:
    role: str
    mode: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    headers: dict[str, str] | None = None
    answer_capability: str | None = None

    @property
    def provider(self) -> str:
        if self.mode in {"docker_ollama", "native_ollama"}:
            return "ollama"
        return self.mode

    @property
    def ollama_base_url(self) -> str | None:
        if self.mode == "docker_ollama":
            return "http://ollama:11434"
        if self.mode == "native_ollama":
            return self.base_url
        return None

    @property
    def uses_docker_ollama(self) -> bool:
        return self.mode == "docker_ollama"


@dataclass(frozen=True)
class SearchSettings:
    opensearch_url: str
    opensearch_index: str
    retrieval_backend: str


@dataclass(frozen=True)
class SummarySettings:
    chunk_timeout_seconds: float
    max_parallel_chunks: int


@dataclass(frozen=True)
class ServiceSettings:
    api_port: int
    web_port: int
    opensearch_port: int
    opensearch_java_opts: str
    ollama_host: str
    summary_worker_limit: int
    summary_worker_poll_interval_seconds: float


@dataclass(frozen=True)
class LibrarianConfig:
    path: Path
    paths: PathSettings
    embedding: ProviderSettings
    generation: ProviderSettings
    search: SearchSettings
    summaries: SummarySettings
    services: ServiceSettings
    codex_executable: str

    @property
    def uses_docker_ollama(self) -> bool:
        return self.embedding.uses_docker_ollama or self.generation.uses_docker_ollama


def default_config_path(*, cwd: Path | None = None) -> Path:
    """Return the documented local or mounted JSON configuration location."""
    if CONTAINER_CONFIG_PATH.parent.exists():
        return CONTAINER_CONFIG_PATH
    root = cwd if cwd is not None else Path.cwd()
    for candidate_root in (root, *root.parents):
        candidate = candidate_root / CONFIG_DIRECTORY_NAME / CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return root / CONFIG_DIRECTORY_NAME / CONFIG_FILENAME


def get_librarian_config(path: str | Path | None = None) -> LibrarianConfig:
    """Load the required JSON file; no environment configuration is consulted."""
    configured_path = Path(path) if path is not None else default_config_path()
    return _load_librarian_config(configured_path.resolve())


def clear_librarian_config_cache() -> None:
    """Clear cached JSON/secret-file values for deterministic tests and reloads."""
    _load_librarian_config.cache_clear()


@lru_cache(maxsize=16)
def _load_librarian_config(path: Path) -> LibrarianConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LibrarianConfigError(
            "Librarian configuration is missing. Copy "
            "config/librarian.example.json to config/librarian.json, then rerun "
            "the launch script."
        ) from exc
    except json.JSONDecodeError as exc:
        raise LibrarianConfigError(
            f"Librarian configuration is not valid JSON near line {exc.lineno}."
        ) from exc

    root = _require_mapping(payload, "Librarian configuration")
    _reject_unknown_keys(
        root,
        {
            "version",
            "paths",
            "embedding",
            "generation",
            "search",
            "summaries",
            "services",
            "codex_executable",
        },
        "Librarian configuration",
    )
    if root.get("version") != 1:
        raise LibrarianConfigError("Librarian configuration version must be the number 1.")

    config_root = path.parent.resolve()
    return LibrarianConfig(
        path=path,
        paths=_parse_paths(root.get("paths")),
        embedding=_parse_provider(
            root.get("embedding"), role="embedding", config_root=config_root
        ),
        generation=_parse_provider(
            root.get("generation"), role="generation", config_root=config_root
        ),
        search=_parse_search(root.get("search")),
        summaries=_parse_summaries(root.get("summaries")),
        services=_parse_services(root.get("services")),
        codex_executable=_require_string(root.get("codex_executable"), "codex_executable"),
    )


def resolve_books_dir(books_dir: str | Path | None = None) -> Path:
    return Path(books_dir).expanduser() if books_dir is not None else Path(
        get_librarian_config().paths.books_dir
    ).expanduser()


def resolve_database_url(database_url: str | None = None) -> str:
    return database_url or get_librarian_config().paths.database_url


def resolve_embedding_provider(embedding_provider: str | None = None) -> str:
    return embedding_provider or get_librarian_config().embedding.provider


def resolve_embedding_model(embedding_model: str | None = None) -> str:
    return embedding_model or get_librarian_config().embedding.model


def resolve_generation_provider(generation_provider: str | None = None) -> str:
    return generation_provider or get_librarian_config().generation.provider


def resolve_generation_model(generation_model: str | None = None) -> str:
    return generation_model or get_librarian_config().generation.model


def resolve_generation_answer_capability() -> str:
    """Return the configured generation capability without model-name guessing."""
    return get_librarian_config().generation.answer_capability or "quality"


def resolve_embedding_ollama_base_url(ollama_base_url: str | None = None) -> str:
    if ollama_base_url:
        return _validate_http_url(ollama_base_url, "ollama_base_url")
    configured = get_librarian_config().embedding.ollama_base_url
    if not configured:
        raise LibrarianConfigError("The embedding provider is not configured for Ollama.")
    return configured


def resolve_generation_ollama_base_url(ollama_base_url: str | None = None) -> str:
    if ollama_base_url:
        return _validate_http_url(ollama_base_url, "ollama_base_url")
    configured = get_librarian_config().generation.ollama_base_url
    if not configured:
        raise LibrarianConfigError("The generation provider is not configured for Ollama.")
    return configured


def resolve_ollama_base_url(ollama_base_url: str | None = None) -> str:
    """Compatibility alias for callers that select the embedding provider."""
    return resolve_embedding_ollama_base_url(ollama_base_url)


def resolve_embedding_openai_compatible() -> tuple[str | None, str | None, dict[str, str]]:
    selection = get_librarian_config().embedding
    return selection.base_url, selection.api_key, dict(selection.headers or {})


def resolve_generation_openai_compatible() -> tuple[str | None, str | None, dict[str, str]]:
    selection = get_librarian_config().generation
    return selection.base_url, selection.api_key, dict(selection.headers or {})


def resolve_opensearch_url(opensearch_url: str | None = None) -> str:
    return _validate_http_url(opensearch_url, "opensearch_url") if opensearch_url else get_librarian_config().search.opensearch_url


def resolve_opensearch_index(opensearch_index: str | None = None) -> str:
    return _validate_opensearch_index(
        opensearch_index or get_librarian_config().search.opensearch_index
    )


def resolve_chat_retrieval_backend(backend: str | None = None) -> str:
    resolved = (backend or get_librarian_config().search.retrieval_backend).strip().casefold()
    if resolved not in {"auto", "opensearch", "sqlite"}:
        raise ValueError("chat retrieval backend must be one of: auto, opensearch, sqlite")
    return resolved


def resolve_codex_executable(codex_executable: str | None = None) -> str:
    return codex_executable or get_librarian_config().codex_executable


def resolve_chunk_summary_timeout_seconds(timeout_seconds: float | None = None) -> float:
    resolved = timeout_seconds if timeout_seconds is not None else get_librarian_config().summaries.chunk_timeout_seconds
    if resolved <= 0:
        raise ValueError("chunk summary timeout must be greater than zero")
    return resolved


def resolve_max_parallel_chunk_summaries(max_parallel: int | None = None) -> int:
    resolved = max_parallel if max_parallel is not None else get_librarian_config().summaries.max_parallel_chunks
    if resolved < 1:
        raise ValueError("max parallel chunk summaries must be at least one")
    return resolved


def sqlite_path_from_url(database_url: str) -> Path:
    if database_url == "sqlite:///:memory:":
        return Path(":memory:")
    if not database_url.startswith("sqlite:///"):
        raise ValueError(f"unsupported database URL for SQLite adapter: {database_url}")
    path = database_url.removeprefix("sqlite:///")
    return Path(path if path.startswith("/") else path).expanduser()


def _parse_paths(value: object) -> PathSettings:
    paths = _require_mapping(value, "paths")
    _reject_unknown_keys(paths, {"books_dir", "host_books_dir", "database_url", "log_file"}, "paths")
    return PathSettings(
        books_dir=_require_string(paths.get("books_dir"), "paths.books_dir"),
        host_books_dir=_require_string(paths.get("host_books_dir"), "paths.host_books_dir"),
        database_url=_require_string(paths.get("database_url"), "paths.database_url"),
        log_file=_require_string(paths.get("log_file"), "paths.log_file"),
    )


def _parse_provider(value: object, *, role: str, config_root: Path) -> ProviderSettings:
    provider = _require_mapping(value, role)
    _reject_unknown_keys(
        provider,
        {
            "mode",
            "model",
            "base_url",
            "api_key_file",
            "headers",
            "header_files",
            "answer_capability",
        },
        role,
    )
    mode = _require_string(provider.get("mode"), f"{role}.mode").casefold()
    if mode not in _ALLOWED_PROVIDER_MODES or (mode == "codex" and role != "generation"):
        allowed = "docker_ollama, native_ollama, openai_compatible"
        if role == "generation":
            allowed += ", codex"
        raise LibrarianConfigError(f"{role}.mode must be one of: {allowed}")
    model = _require_string(provider.get("model"), f"{role}.model")
    if role != "generation" and "answer_capability" in provider:
        raise LibrarianConfigError("embedding.answer_capability is not supported")
    answer_capability = (
        _parse_answer_capability(provider.get("answer_capability"), mode=mode)
        if role == "generation"
        else None
    )

    if mode in {"docker_ollama", "codex"}:
        _reject_present(provider, {"base_url", "api_key_file", "headers", "header_files"}, role)
        return ProviderSettings(
            role=role,
            mode=mode,
            model=model,
            answer_capability=answer_capability,
        )
    if mode == "native_ollama":
        _reject_present(provider, {"api_key_file", "headers", "header_files"}, role)
        return ProviderSettings(
            role=role,
            mode=mode,
            model=model,
            base_url=_validate_http_url(
                _require_string(provider.get("base_url"), f"{role}.base_url"),
                f"{role}.base_url",
            ),
            answer_capability=answer_capability,
        )

    api_key = _read_secret_file(
        _require_string(provider.get("api_key_file"), f"{role}.api_key_file"),
        config_root=config_root,
        label=f"{role}.api_key_file",
    )
    headers = _parse_headers(provider.get("headers"), role=role)
    for header_name, reference in _parse_header_files(provider.get("header_files"), role=role).items():
        headers[header_name] = _read_secret_file(
            reference,
            config_root=config_root,
            label=f"{role}.header_files",
        )
    return ProviderSettings(
        role=role,
        mode=mode,
        model=model,
        base_url=_validate_openai_url(
            _require_string(provider.get("base_url"), f"{role}.base_url"),
            f"{role}.base_url",
        ),
        api_key=api_key,
        headers=headers,
        answer_capability=answer_capability,
    )


def _parse_answer_capability(value: object, *, mode: str) -> str:
    if value is None:
        return "lightweight" if mode == "docker_ollama" else "quality"
    return _parse_answer_capability_value(value, field_name="generation.answer_capability")


def _parse_answer_capability_value(value: object, *, field_name: str) -> str:
    capability = _require_string(value, field_name).casefold()
    if capability not in _ALLOWED_ANSWER_CAPABILITIES:
        raise LibrarianConfigError(f"{field_name} must be quality or lightweight")
    return capability


def _parse_search(value: object) -> SearchSettings:
    search = _require_mapping(value, "search")
    _reject_unknown_keys(search, {"opensearch_url", "opensearch_index", "retrieval_backend"}, "search")
    backend = _require_string(search.get("retrieval_backend"), "search.retrieval_backend").casefold()
    if backend not in {"auto", "opensearch", "sqlite"}:
        raise LibrarianConfigError("search.retrieval_backend must be auto, opensearch, or sqlite")
    return SearchSettings(
        opensearch_url=_validate_http_url(
            _require_string(search.get("opensearch_url"), "search.opensearch_url"),
            "search.opensearch_url",
        ),
        opensearch_index=_validate_opensearch_index(
            _require_string(search.get("opensearch_index"), "search.opensearch_index")
        ),
        retrieval_backend=backend,
    )


def _parse_summaries(value: object) -> SummarySettings:
    summaries = _require_mapping(value, "summaries")
    _reject_unknown_keys(summaries, {"chunk_timeout_seconds", "max_parallel_chunks"}, "summaries")
    timeout = _require_positive_number(summaries.get("chunk_timeout_seconds"), "summaries.chunk_timeout_seconds")
    parallel = _require_positive_int(summaries.get("max_parallel_chunks"), "summaries.max_parallel_chunks")
    return SummarySettings(chunk_timeout_seconds=timeout, max_parallel_chunks=parallel)


def _parse_services(value: object) -> ServiceSettings:
    services = _require_mapping(value, "services")
    _reject_unknown_keys(
        services,
        {
            "api_port",
            "web_port",
            "opensearch_port",
            "opensearch_java_opts",
            "ollama_host",
            "summary_worker_limit",
            "summary_worker_poll_interval_seconds",
        },
        "services",
    )
    return ServiceSettings(
        api_port=_require_port(services.get("api_port"), "services.api_port"),
        web_port=_require_port(services.get("web_port"), "services.web_port"),
        opensearch_port=_require_port(services.get("opensearch_port"), "services.opensearch_port"),
        opensearch_java_opts=_require_string(
            services.get("opensearch_java_opts"), "services.opensearch_java_opts"
        ),
        ollama_host=_require_string(services.get("ollama_host"), "services.ollama_host"),
        summary_worker_limit=_require_positive_int(
            services.get("summary_worker_limit"), "services.summary_worker_limit"
        ),
        summary_worker_poll_interval_seconds=_require_positive_number(
            services.get("summary_worker_poll_interval_seconds"),
            "services.summary_worker_poll_interval_seconds",
        ),
    )


def _parse_headers(value: object, *, role: str) -> dict[str, str]:
    if value is None:
        return {}
    headers = _require_mapping(value, f"{role}.headers")
    normalized: dict[str, str] = {}
    for name, header_value in headers.items():
        _validate_header_name(name, f"{role}.headers")
        normalized[name] = _require_string(header_value, f"{role}.headers.{name}")
    return normalized


def _parse_header_files(value: object, *, role: str) -> dict[str, str]:
    if value is None:
        return {}
    headers = _require_mapping(value, f"{role}.header_files")
    normalized: dict[str, str] = {}
    for name, reference in headers.items():
        _validate_header_name(name, f"{role}.header_files")
        normalized[name] = _require_string(reference, f"{role}.header_files.{name}")
    return normalized


def _read_secret_file(reference: str, *, config_root: Path, label: str) -> str:
    relative = Path(reference)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) < 2
        or relative.parts[0] != "secrets"
    ):
        raise LibrarianConfigError(f"{label} must reference a file under config/secrets")
    candidate = (config_root / relative).resolve()
    secrets_root = (config_root / "secrets").resolve()
    try:
        candidate.relative_to(secrets_root)
    except ValueError as exc:
        raise LibrarianConfigError(f"{label} must reference a file under config/secrets") from exc
    try:
        secret = candidate.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError, UnicodeDecodeError) as exc:
        raise LibrarianConfigError(f"{label} could not be read from config/secrets") from exc
    if not secret or "\x00" in secret:
        raise LibrarianConfigError(f"{label} must contain a non-empty secret value")
    return secret


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LibrarianConfigError(f"{label} must be a JSON object")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise LibrarianConfigError(f"{label} must be a non-empty, single-line string")
    return value.strip()


def _require_positive_number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise LibrarianConfigError(f"{label} must be a number greater than zero")
    return float(value)


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise LibrarianConfigError(f"{label} must be an integer of at least one")
    return value


def _require_port(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
        raise LibrarianConfigError(f"{label} must be a TCP port between 1 and 65535")
    return value


def _validate_header_name(name: object, label: str) -> None:
    if not isinstance(name, str) or not name or any(char not in _HTTP_HEADER_NAME for char in name):
        raise LibrarianConfigError(f"{label} keys must be valid HTTP header names")
    if name.casefold() in {"authorization", "content-type", "host"}:
        raise LibrarianConfigError(f"{label} cannot override {name}")


def _validate_http_url(value: str, label: str) -> str:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise LibrarianConfigError(f"{label} must be a valid http:// or https:// URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LibrarianConfigError(
            f"{label} must be an http:// or https:// URL without credentials, query parameters, or fragments"
        )
    return value.rstrip("/")


def _validate_openai_url(value: str, label: str) -> str:
    try:
        return validate_openai_compatible_base_url(value)
    except OpenAICompatibleEndpointError as exc:
        raise LibrarianConfigError(
            f"{label} must be an http(s) URL without credentials, query parameters, or fragments"
        ) from exc


def _validate_opensearch_index(index_name: str) -> str:
    cleaned = index_name.strip().casefold()
    if not cleaned or any(character.isspace() for character in cleaned):
        raise LibrarianConfigError("OpenSearch index name must not be empty or contain whitespace")
    return cleaned


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise LibrarianConfigError(f"{label} has unsupported field(s): {', '.join(unknown)}")


def _reject_present(value: dict[str, Any], names: set[str], label: str) -> None:
    present = sorted(name for name in names if name in value)
    if present:
        raise LibrarianConfigError(f"{label} cannot set: {', '.join(present)}")
