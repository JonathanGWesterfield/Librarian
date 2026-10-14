"""Tests for the strict non-secret R2 gRPC broker runtime document."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_contracts.broker_server_config import (
    BrokerServerConfigError,
    build_broker_server_runtime_config,
    load_broker_server_runtime_config,
    parse_broker_server_runtime_config,
    serialize_broker_server_runtime_config,
)


class BrokerServerRuntimeConfigTests(unittest.TestCase):
    """The R2 server accepts no caller path, target, or credential fields."""

    def test_round_trip_has_only_model_and_answer_capability(self) -> None:
        config = build_broker_server_runtime_config(
            model="gpt-5.6-sol", answer_capability="quality"
        )

        payload = json.loads(serialize_broker_server_runtime_config(config))

        self.assertEqual(
            payload,
            {
                "version": 1,
                "generation": {
                    "model": "gpt-5.6-sol",
                    "answer_capability": "quality",
                },
            },
        )
        self.assertEqual(parse_broker_server_runtime_config(json.dumps(payload)), config)

    def test_rejects_legacy_secret_client_and_unknown_fields(self) -> None:
        valid = {
            "version": 1,
            "generation": {"model": "gpt-5.6-sol", "answer_capability": "quality"},
        }
        cases = (
            {**valid, "services": {}},
            {
                "version": 1,
                "generation": {
                    "model": "gpt-5.6-sol",
                    "answer_capability": "quality",
                    "api_key_file": "secrets/bridge.token",
                },
            },
            {"version": 1, "generation": {"model": "gpt-5.6-sol"}},
        )

        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(BrokerServerConfigError):
                parse_broker_server_runtime_config(json.dumps(payload))

    def test_loader_rejects_a_symlinked_runtime_mount(self) -> None:
        config = build_broker_server_runtime_config(
            model="gpt-5.6-sol", answer_capability="quality"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text(serialize_broker_server_runtime_config(config), encoding="utf-8")
            mounted = root / "librarian.json"
            mounted.symlink_to(target)

            with self.assertRaisesRegex(BrokerServerConfigError, "could not read"):
                load_broker_server_runtime_config(mounted)


if __name__ == "__main__":
    unittest.main()
