"""Regression coverage for Librarian's authoritative JSON configuration."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))
RESOLVER_PATH = REPO_ROOT / "scripts" / "resolve_provider_config.py"
SPEC = importlib.util.spec_from_file_location("librarian_compose_resolver", RESOLVER_PATH)
assert SPEC is not None and SPEC.loader is not None
resolver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resolver
SPEC.loader.exec_module(resolver)

from librarian_config.config import (  # noqa: E402
    LibrarianConfigError,
    clear_librarian_config_cache,
    get_librarian_config,
    resolve_generation_answer_capability,
)


class LibrarianConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_librarian_config_cache()

    def test_example_is_complete_and_ignores_legacy_environment(self) -> None:
        """JSON stays authoritative even when a caller exports old variables."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "librarian.json"
            path.write_text(
                (REPO_ROOT / "config" / "librarian.example.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "LIBRARIAN_DATABASE_URL": "sqlite:///ignored.db",
                    "LIBRARIAN_GENERATION_MODEL": "ignored-model",
                    "LIBRARIAN_OPENSEARCH_URL": "http://ignored.invalid",
                },
                clear=False,
            ):
                config = get_librarian_config(path)

        self.assertEqual(config.paths.database_url, "sqlite:////data/librarian.db")
        self.assertEqual(config.generation.model, "qwen2.5:1.5b")
        self.assertEqual(config.generation.answer_capability, "lightweight")
        self.assertEqual(config.search.opensearch_url, "http://opensearch:9200")

    def test_generation_capability_is_a_configured_product_default(self) -> None:
        """Capability is not inferred from a generation model name."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "librarian.json"
            _write_config(
                path,
                generation={
                    "mode": "native_ollama",
                    "model": "qwen2.5:7b",
                    "base_url": "http://host.docker.internal:11434",
                    "answer_capability": "quality",
                },
            )
            with patch("librarian_config.config.default_config_path", return_value=path):
                self.assertEqual(resolve_generation_answer_capability(), "quality")

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["generation"]["answer_capability"] = "unknown"
            path.write_text(json.dumps(payload), encoding="utf-8")
            clear_librarian_config_cache()
            with self.assertRaisesRegex(LibrarianConfigError, "quality or lightweight"):
                get_librarian_config(path)

    def test_supported_provider_modes_are_independent(self) -> None:
        """Embedding and generation transports are independently selected."""
        modes = ("docker_ollama", "native_ollama", "openai_compatible")
        for embedding_mode in modes:
            for generation_mode in (*modes, "codex"):
                with self.subTest(embedding=embedding_mode, generation=generation_mode):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        path = root / "librarian.json"
                        _write_config(
                            path,
                            embedding=_selection(embedding_mode, "embedding"),
                            generation=_selection(generation_mode, "generation"),
                        )
                        _write_secret_files(root, embedding_mode, generation_mode)
                        config = get_librarian_config(path)
                    self.assertEqual(
                        config.embedding.provider,
                        "ollama" if embedding_mode.endswith("ollama") else "openai_compatible",
                    )
                    self.assertEqual(
                        config.generation.provider,
                        "ollama" if generation_mode.endswith("ollama") else generation_mode,
                    )
                    clear_librarian_config_cache()

    def test_secrets_are_restricted_to_config_secrets_and_never_rendered(self) -> None:
        """Compose receives service wiring, not provider credentials."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "librarian.json"
            _write_config(
                path,
                embedding=_selection("openai_compatible", "embedding"),
                generation=_selection("openai_compatible", "generation"),
            )
            _write_secret_files(root, "openai_compatible", "openai_compatible")
            config = get_librarian_config(path)
            rendered = json.dumps(resolver.render_compose_override(config))

            self.assertEqual(config.embedding.api_key, "embedding-secret")
            self.assertNotIn("embedding-secret", rendered)
            self.assertNotIn("generation-secret", rendered)

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["embedding"]["api_key_file"] = "unprotected.token"
            path.write_text(json.dumps(payload), encoding="utf-8")
            clear_librarian_config_cache()
            with self.assertRaisesRegex(LibrarianConfigError, "under config/secrets"):
                get_librarian_config(path)

    def test_compose_state_and_override_are_json_derived(self) -> None:
        """Resolved ports and Docker-Ollama profile follow JSON, not shell state."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "librarian.json"
            _write_config(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["services"]["api_port"] = 8059
            payload["services"]["web_port"] = 3059
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = get_librarian_config(path)

        self.assertEqual(
            resolver.render_state(config),
            {"docker_ollama_enabled": True, "api_port": 8059, "web_port": 3059},
        )
        override = resolver.render_compose_override(config)
        services = override["services"]
        self.assertEqual(services["api"]["ports"], ["8059:8000"])
        self.assertEqual(services["web"]["ports"], ["3059:8080"])
        self.assertEqual(services["ollama-init"]["environment"], {"OLLAMA_INIT_MODELS": "all-minilm,qwen2.5:1.5b"})


def _write_config(
    path: Path,
    *,
    embedding: dict[str, object] | None = None,
    generation: dict[str, object] | None = None,
) -> None:
    payload = json.loads(
        (REPO_ROOT / "config" / "librarian.example.json").read_text(encoding="utf-8")
    )
    if embedding is not None:
        payload["embedding"] = embedding
    if generation is not None:
        payload["generation"] = generation
    path.write_text(json.dumps(payload), encoding="utf-8")


def _selection(mode: str, role: str) -> dict[str, object]:
    if mode == "docker_ollama":
        return {"mode": mode, "model": f"{role}-docker"}
    if mode == "native_ollama":
        return {
            "mode": mode,
            "model": f"{role}-native",
            "base_url": "http://host.docker.internal:11434",
        }
    if mode == "codex":
        return {"mode": mode, "model": "codex"}
    return {
        "mode": mode,
        "model": f"{role}-gateway",
        "base_url": "http://host.docker.internal:3000/v1",
        "api_key_file": f"secrets/{role}.token",
    }


def _write_secret_files(root: Path, embedding_mode: str, generation_mode: str) -> None:
    secrets = root / "secrets"
    secrets.mkdir(exist_ok=True)
    if embedding_mode == "openai_compatible":
        (secrets / "embedding.token").write_text("embedding-secret\n", encoding="utf-8")
    if generation_mode == "openai_compatible":
        (secrets / "generation.token").write_text("generation-secret\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
