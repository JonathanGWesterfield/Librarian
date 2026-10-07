"""Exercise the pre-transport Docker-broker guard from every host CLI."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
BOUNDARY_INVENTORY_PATH = REPO_ROOT / "tests/fixtures/answer_delivery/v1/boundary_inventory.json"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.generation import create_configured_generator
from librarian_config.config import (
    CONTAINER_CONFIG_PATH,
    LibrarianConfigError,
    clear_librarian_config_cache,
    enforce_docker_broker_host_guard,
    get_librarian_config,
)
from librarian_evaluation.llm_judge import create_judge

HOST_CLI_CASES = (
    ("scripts/chat.py", ["Who is Eto Demerzel?"], 2),
    ("scripts/summarize.py", ["book", "--book-id", "fixture-book"], 2),
    ("scripts/tags.py", ["generate", "--book-id", "fixture-book"], 2),
    ("scripts/genres.py", ["generate", "--book-id", "fixture-book"], 2),
    ("scripts/process_summary_jobs.py", [], 2),
    ("scripts/process_metadata_jobs.py", [], 2),
    ("scripts/play/librarian.py", ["recommend", "fixture query"], 2),
    ("scripts/play/summary_jobs.py", ["process"], 2),
    ("scripts/evaluate_retrieval.py", ["--llm-judge"], 1),
)


class HostDockerBrokerGuardTests(unittest.TestCase):
    """A host cannot turn the private broker into an accidental public client."""

    def tearDown(self) -> None:
        clear_librarian_config_cache()

    def test_factory_rejects_default_broker_before_creating_a_client(self) -> None:
        with _docker_broker_config():
            with patch(
                "librarian_chat.generation.create_generator",
                side_effect=AssertionError("the host guard must run before client creation"),
            ) as create:
                with self.assertRaisesRegex(
                    LibrarianConfigError,
                    "configured generation cannot use docker_codex_broker from the host",
                ):
                    create_configured_generator()

        create.assert_not_called()

    def test_forged_execution_principal_does_not_bypass_the_host_guard(self) -> None:
        with _docker_broker_config():
            with patch.dict(
                os.environ,
                {"LIBRARIAN_EXECUTION_PRINCIPAL": "api"},
                clear=False,
            ):
                with self.assertRaisesRegex(
                    LibrarianConfigError,
                    "cannot use docker_codex_broker from the host",
                ):
                    enforce_docker_broker_host_guard(entrypoint="host test")

    def test_compose_configuration_is_not_rejected_during_r0_compatibility(self) -> None:
        with _docker_broker_config():
            config = get_librarian_config()

        enforce_docker_broker_host_guard(
            entrypoint="container test",
            config=replace(config, path=CONTAINER_CONFIG_PATH.resolve()),
        )

    def test_explicit_non_docker_providers_remain_valid_host_choices(self) -> None:
        for provider in ("codex", "ollama", "noop"):
            with self.subTest(provider=provider):
                enforce_docker_broker_host_guard(
                    generation_provider=provider,
                    entrypoint="host test",
                )

    def test_broker_judge_is_rejected_before_it_can_construct_an_http_client(self) -> None:
        with _docker_broker_config():
            with self.assertRaisesRegex(
                LibrarianConfigError,
                "Docker Codex broker judge cannot use docker_codex_broker from the host",
            ):
                create_judge(
                    "docker_codex_broker",
                    model="gpt-5.6-sol",
                    ollama_base_url="http://unused",
                    broker_base_url="http://codex-broker:3000/v1",
                    broker_api_key="fixture-token",
                )

    def test_host_cli_suite_covers_the_complete_boundary_inventory(self) -> None:
        inventory = json.loads(BOUNDARY_INVENTORY_PATH.read_text(encoding="utf-8"))
        expected = {entry["source"] for entry in inventory["host_entrypoints"]}
        covered = {relative_path for relative_path, _argv, _exit in HOST_CLI_CASES}

        self.assertEqual(covered, expected)

    def test_every_documented_host_entrypoint_rejects_broker_use_before_io(self) -> None:
        """The inventory's host rows must fail before a target or subprocess exists."""
        for relative_path, argv, expected_exit in HOST_CLI_CASES:
            with self.subTest(entrypoint=relative_path):
                with _docker_broker_config():
                    module = _load_script_module(relative_path)
                    with (
                        patch.dict(
                            os.environ,
                            {"LIBRARIAN_EXECUTION_PRINCIPAL": "api"},
                            clear=False,
                        ),
                        patch(
                            "urllib.request.urlopen",
                            side_effect=AssertionError("the host guard must run before HTTP"),
                        ) as urlopen,
                        patch(
                            "subprocess.Popen",
                            side_effect=AssertionError(
                                "the host guard must run before a provider subprocess"
                            ),
                        ) as popen,
                    ):
                        if relative_path == "scripts/evaluate_retrieval.py":
                            with patch.object(sys, "argv", [relative_path, *argv]):
                                exit_code = module.main()
                        else:
                            exit_code = module.main(argv)

                self.assertEqual(exit_code, expected_exit)
                urlopen.assert_not_called()
                popen.assert_not_called()


@contextmanager
def _docker_broker_config():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "librarian.json"
        payload = json.loads(
            (REPO_ROOT / "config" / "librarian.base.json").read_text(encoding="utf-8")
        )
        secrets = root / "secrets"
        secrets.mkdir()
        (secrets / "codex-bridge-token.txt").write_text("fixture-token\n", encoding="utf-8")
        path.write_text(json.dumps(payload), encoding="utf-8")
        with patch("librarian_config.config.default_config_path", return_value=path):
            clear_librarian_config_cache()
            yield
        clear_librarian_config_cache()


def _load_script_module(relative_path: str):
    path = REPO_ROOT / relative_path
    module_name = f"host_guard_{path.stem}_{abs(hash(relative_path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
