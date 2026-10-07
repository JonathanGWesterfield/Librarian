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
from pathlib import Path

from librarian_config.config import (
    LibrarianConfig,
    LibrarianConfigError,
    get_librarian_config,
)
from librarian_contracts.runtime_config import (
    CLIENT_CREDENTIAL_ROLES,
    build_broker_client_runtime_config,
    serialize_broker_client_runtime_config,
)


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
    args = parser.parse_args()
    try:
        config = get_librarian_config(args.config)
        write_json(
            args.compose_output,
            render_compose_override(config, publish_host_ports=not args.no_host_ports),
        )
        write_json(args.state_output, render_state(config))
        if args.broker_runtime_output_dir is not None:
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


if __name__ == "__main__":
    raise SystemExit(main())
