"""Render safe Docker Compose wiring from Librarian's JSON configuration.

The resolver runs in Docker and reads only ``config/librarian.json``. It emits
non-secret service settings and a profile-selection state file. API keys and
secret headers stay in ignored files beneath mounted ``config/secrets/`` and
are read by the application at runtime.

Examples:
    docker compose --profile config-resolver run --rm --build config-resolver
    python scripts/resolve_provider_config.py \\
      --config config/librarian.example.json \\
      --compose-output /tmp/librarian.compose.json \\
      --state-output /tmp/librarian.state.json
"""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from librarian_config.config import (
    LibrarianConfig,
    LibrarianConfigError,
    get_librarian_config,
)
from librarian_contracts.broker_server_config import (
    build_broker_server_runtime_config,
    serialize_broker_server_runtime_config,
)
from librarian_contracts.compose_security import BROKER_SECRET_NAMES
from librarian_contracts.runtime_config import (
    CLIENT_CREDENTIAL_ROLES,
    BrokerClientRuntimeConfig,
    build_broker_client_runtime_config,
    serialize_broker_client_runtime_config,
)

R2_BROKER_SERVICE = "codex-broker"
R2_BROKER_SECRET_ROLES = tuple(BROKER_SECRET_NAMES)


def render_compose_override(
    config: LibrarianConfig, *, publish_host_ports: bool = True
) -> dict[str, object]:
    """Return literal, non-secret Compose fields selected by JSON configuration."""
    docker_models = _docker_ollama_models(config)
    services: dict[str, dict[str, object]] = {
        "opensearch": {
            "environment": {"OPENSEARCH_JAVA_OPTS": config.services.opensearch_java_opts},
        },
        "ollama": {"environment": {"OLLAMA_HOST": config.services.ollama_host}},
        "ollama-init": {"environment": {"OLLAMA_INIT_MODELS": ",".join(docker_models)}},
        "api": {
            "volumes": [_books_volume(config.paths.host_books_dir)],
        },
        "web": {},
        "summary-worker": {
            "command": [
                "python",
                "scripts/process_summary_jobs.py",
                "--watch",
                "--limit",
                str(config.services.summary_worker_limit),
                "--poll-interval-seconds",
                str(config.services.summary_worker_poll_interval_seconds),
            ]
        },
    }
    if config.uses_docker_codex_broker:
        # State both dependencies in the generated override rather than relying
        # on Compose's map-merge behavior. The API must never trade its
        # OpenSearch readiness guarantee for the optional generation broker.
        runtime_dependencies = {
            "opensearch": {"condition": "service_healthy"},
            "codex-broker": {"condition": "service_healthy"},
        }
        services["api"]["depends_on"] = runtime_dependencies
        services["summary-worker"]["depends_on"] = runtime_dependencies
    if publish_host_ports:
        services["opensearch"]["ports"] = [f"{config.services.opensearch_port}:9200"]
        services["api"]["ports"] = [f"{config.services.api_port}:8000"]
        services["web"]["ports"] = [f"{config.services.web_port}:8080"]
    return {"services": services}


def render_state(config: LibrarianConfig) -> dict[str, bool | int]:
    """Return non-secret launch state derived from the authoritative JSON file."""
    return {
        "docker_ollama_enabled": config.uses_docker_ollama,
        "docker_codex_broker_enabled": config.uses_docker_codex_broker,
        "api_port": config.services.api_port,
        "web_port": config.services.web_port,
    }


def render_broker_client_runtime_configs(config: LibrarianConfig) -> dict[str, str]:
    """Render one sanitized future gRPC client file for every Docker caller.

    The user-owned configuration may contain a host-relative credential path and
    the resolved ``LibrarianConfig`` may hold its secret value. Neither crosses
    this boundary: generated runtime files contain only the model, capability,
    fixed broker target, contract version, and caller's logical role.
    """
    if not config.uses_docker_codex_broker:
        return {}

    return {
        role: serialize_broker_client_runtime_config(
            build_broker_client_runtime_config(
                model=config.generation.model,
                answer_capability=config.generation.answer_capability or "quality",
                credential_role=role,
            )
        )
        for role in sorted(CLIENT_CREDENTIAL_ROLES)
    }


def write_broker_client_runtime_configs(output_directory: Path, config: LibrarianConfig) -> list[Path]:
    """Synchronize per-client JSON under the resolver-owned runtime directory."""

    rendered = render_broker_client_runtime_configs(config)
    written_paths: list[Path] = []
    for role in sorted(CLIENT_CREDENTIAL_ROLES):
        path = output_directory / role / "librarian.json"
        content = rendered.get(role)
        if content is None:
            _remove_stale_broker_client_runtime_config(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(path)
    return written_paths


def render_r2_runtime_configs(config: LibrarianConfig) -> dict[str, str]:
    """Render the one strict non-secret runtime document for every R2 role.

    The caller documents remain owned by ``runtime_config`` and retain its
    fixed target, protocol, and credential-role validation.  The broker has a
    narrower server document with no client role, target, credential path, or
    legacy provider key reference.
    """

    rendered = render_broker_client_runtime_configs(config)
    if not rendered:
        return {}
    for role in ("api", "summary-worker", "metadata-worker", "evaluator"):
        client = build_broker_client_runtime_config(
            model=config.generation.model,
            answer_capability=config.generation.answer_capability or "quality",
            credential_role=role,
        )
        rendered[role] = _serialize_r2_application_runtime_config(
            config,
            client,
            runtime_mode="r2_" + role.replace("-", "_"),
        )
    rendered[R2_BROKER_SERVICE] = serialize_broker_server_runtime_config(
        build_broker_server_runtime_config(
            model=config.generation.model,
            answer_capability=config.generation.answer_capability or "quality",
        )
    )
    return rendered


def _serialize_r2_application_runtime_config(
    config: LibrarianConfig,
    client_config: BrokerClientRuntimeConfig,
    *,
    runtime_mode: str,
) -> str:
    """Render one non-secret R2 application configuration document.

    Each caller keeps the safe local storage, embedding, retrieval, and service
    settings it needs beside the strict broker section. This keeps one versioned
    file per role without copying a provider credential or host-relative path
    across the resolver boundary.
    """

    if config.embedding.mode == "openai_compatible":
        raise LibrarianConfigError(
            "R2 application requires docker_ollama or native_ollama embeddings; "
            "credential-bearing embeddings cannot enter the runtime file"
        )
    broker = client_config
    payload = {
        "version": 2,
        "runtime": {"mode": runtime_mode},
        "paths": {
            "books_dir": config.paths.books_dir,
            "host_books_dir": config.paths.host_books_dir,
            "database_url": config.paths.database_url,
            "log_file": config.paths.log_file,
        },
        "embedding": _serialize_safe_embedding(config),
        "generation": {
            "mode": "r2_grpc",
            "model": config.generation.model,
            "answer_capability": config.generation.answer_capability or "quality",
        },
        "search": {
            "opensearch_url": config.search.opensearch_url,
            "opensearch_index": config.search.opensearch_index,
            "retrieval_backend": config.search.retrieval_backend,
        },
        "summaries": {
            "chunk_timeout_seconds": config.summaries.chunk_timeout_seconds,
            "max_parallel_chunks": config.summaries.max_parallel_chunks,
        },
        "semantic_source_selector": {
            "enabled": False,
            "provider": "codex",
            "model": config.generation.model,
        },
        "services": {
            "api_port": config.services.api_port,
            "web_port": config.services.web_port,
            "opensearch_port": config.services.opensearch_port,
            "opensearch_java_opts": config.services.opensearch_java_opts,
            "ollama_host": config.services.ollama_host,
            "summary_worker_limit": config.services.summary_worker_limit,
            "summary_worker_poll_interval_seconds": config.services.summary_worker_poll_interval_seconds,
        },
        "answer_delivery": {
            "codex_broker": {
                "transport": "grpc",
                "target": broker.target,
                "contract_major": broker.contract_major,
                "contract_minor": broker.contract_minor,
                "credential_role": broker.credential_role,
            }
        },
    }
    if runtime_mode == "r2_api":
        payload["chat"] = {"delivery_mode": config.chat.delivery_mode}
    return json.dumps(payload, indent=2) + "\n"


def _serialize_safe_embedding(config: LibrarianConfig) -> dict[str, str]:
    embedding = {"mode": config.embedding.mode, "model": config.embedding.model}
    if config.embedding.mode == "native_ollama":
        if not config.embedding.base_url:
            raise LibrarianConfigError("native_ollama embedding configuration is incomplete")
        embedding["base_url"] = config.embedding.base_url
    return embedding


def write_r2_runtime_configs(output_directory: Path, config: LibrarianConfig) -> list[Path]:
    """Synchronize all R2 broker/caller files after validating secret sources."""

    validate_r2_broker_secret_sources(config)
    rendered = render_r2_runtime_configs(config)
    written_paths: list[Path] = []
    for service in (*sorted(CLIENT_CREDENTIAL_ROLES), R2_BROKER_SERVICE):
        path = output_directory / service / "librarian.json"
        content = rendered.get(service)
        if content is None:
            _remove_stale_broker_client_runtime_config(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(path)
    return written_paths


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write deterministic JSON used by the launcher and Compose override."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Librarian JSON configuration path.")
    parser.add_argument(
        "--no-host-ports",
        action="store_true",
        help="Do not publish API, web, or OpenSearch ports for isolated verification.",
    )
    parser.add_argument(
        "--compose-output", type=Path, required=True, help="Generated non-secret Compose override path."
    )
    parser.add_argument(
        "--state-output", type=Path, required=True, help="Generated non-secret profile state path."
    )
    parser.add_argument(
        "--broker-runtime-output-dir",
        type=Path,
        help=(
            "Directory for generated per-client broker runtime JSON. "
            "Files are produced only when docker_codex_broker is selected."
        ),
    )
    parser.add_argument(
        "--r2",
        action="store_true",
        help=(
            "Validate all role-specific broker secrets and emit the separate "
            "atomic R2 broker/caller runtime files."
        ),
    )
    args = parser.parse_args()
    try:
        config = get_librarian_config(args.config)
        write_json(
            args.compose_output,
            render_compose_override(config, publish_host_ports=not args.no_host_ports),
        )
        write_json(args.state_output, render_state(config))
        if args.r2 and args.broker_runtime_output_dir is None:
            raise LibrarianConfigError("--r2 requires --broker-runtime-output-dir")
        if args.r2:
            assert args.broker_runtime_output_dir is not None
            write_r2_runtime_configs(args.broker_runtime_output_dir, config)
        elif args.broker_runtime_output_dir is not None:
            write_broker_client_runtime_configs(args.broker_runtime_output_dir, config)
    except LibrarianConfigError as exc:
        parser.error(str(exc))
    print("[librarian] JSON configuration resolved for Docker Compose.")
    return 0


def _docker_ollama_models(config: LibrarianConfig) -> list[str]:
    return [
        selection.model
        for selection in (config.embedding, config.generation)
        if selection.uses_docker_ollama and selection.model != "noop"
    ]


def _books_volume(host_books_dir: str) -> str:
    if not host_books_dir or "\n" in host_books_dir or "\r" in host_books_dir:
        raise LibrarianConfigError("paths.host_books_dir must be a non-empty, single-line path")
    return f"{host_books_dir}:/books:ro"


def _remove_stale_broker_client_runtime_config(path: Path) -> None:
    """Remove only a resolver-owned file when the Docker broker is disabled."""

    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        raise LibrarianConfigError(
            f"broker runtime config path must be a file when present: {path}"
        )


def validate_r2_broker_secret_sources(config: LibrarianConfig) -> None:
    """Reject a partial R2 secret set before it can replace an R0 stack."""

    if not config.uses_docker_codex_broker:
        raise LibrarianConfigError("--r2 requires generation.mode docker_codex_broker")
    secret_directory = config.path.parent / "secrets"
    credential_values: set[str] = set()
    for role in R2_BROKER_SECRET_ROLES:
        credential = _validate_r2_secret_source(secret_directory / BROKER_SECRET_NAMES[role])
        if credential in credential_values:
            raise LibrarianConfigError("R2 broker credential sources must be distinct")
        credential_values.add(credential)


def _validate_r2_secret_source(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise LibrarianConfigError("R2 broker credential sources are incomplete") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LibrarianConfigError("R2 broker credential sources must be regular files")
        with os.fdopen(descriptor, "r", encoding="utf-8") as file:
            descriptor = -1
            credential = file.read().strip()
            if not credential:
                raise LibrarianConfigError("R2 broker credential sources must not be empty")
    except (OSError, UnicodeError) as error:
        raise LibrarianConfigError("R2 broker credential sources are unreadable") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return credential


if __name__ == "__main__":
    raise SystemExit(main())
