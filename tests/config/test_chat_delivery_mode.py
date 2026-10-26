"""Regression coverage for chat delivery-mode configuration and R2 handoff."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_config.config import (
    LibrarianConfigError,
    clear_librarian_config_cache,
    get_librarian_config,
)
from librarian_contracts.runtime_config import (
    RuntimeConfigError,
    parse_broker_client_runtime_config,
)

RESOLVER_PATH = REPO_ROOT / "scripts" / "resolve_provider_config.py"
SPEC = importlib.util.spec_from_file_location("chat_delivery_mode_resolver", RESOLVER_PATH)
assert SPEC is not None and SPEC.loader is not None
resolver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resolver
SPEC.loader.exec_module(resolver)


class ChatDeliveryModeTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_librarian_config_cache()

    def test_base_configuration_declares_buffered_delivery(self) -> None:
        payload = _base_payload()

        self.assertEqual(payload["chat"], {"delivery_mode": "buffered"})
        self.assertEqual(_load(payload).chat.delivery_mode, "buffered")

    def test_missing_chat_section_defaults_to_buffered(self) -> None:
        payload = _base_payload()
        payload.pop("chat")

        self.assertEqual(_load(payload).chat.delivery_mode, "buffered")

    def test_rejects_invalid_chat_values_and_fields(self) -> None:
        invalid_chat_values = (
            None,
            {"delivery_mode": None},
            {"delivery_mode": True},
            {"delivery_mode": "Progressive"},
            {"delivery_mode": "progressive "},
            {"delivery_mode": "disabled"},
            {},
            {"delivery_mode": "buffered", "unexpected": True},
        )
        for chat in invalid_chat_values:
            with self.subTest(chat=chat):
                payload = _base_payload()
                payload["chat"] = chat
                with self.assertRaises(LibrarianConfigError):
                    _load(payload)

    def test_progressive_survives_r2_api_round_trip_only(self) -> None:
        payload = _base_payload()
        payload["chat"] = {"delivery_mode": "progressive"}
        rendered = resolver.render_r2_runtime_configs(_load(payload))

        api_payload = json.loads(rendered["api"])
        self.assertEqual(api_payload["chat"], {"delivery_mode": "progressive"})
        self.assertEqual(parse_broker_client_runtime_config(rendered["api"]).credential_role, "api")
        self.assertEqual(_load(api_payload).chat.delivery_mode, "progressive")

        for role in ("summary-worker", "metadata-worker", "evaluator"):
            with self.subTest(role=role):
                self.assertNotIn("chat", json.loads(rendered[role]))

    def test_r2_api_without_chat_defaults_to_buffered(self) -> None:
        rendered = resolver.render_r2_runtime_configs(_load(_base_payload()))
        api_payload = json.loads(rendered["api"])
        api_payload.pop("chat")

        self.assertEqual(
            parse_broker_client_runtime_config(json.dumps(api_payload)).credential_role,
            "api",
        )
        self.assertEqual(_load(api_payload).chat.delivery_mode, "buffered")

        api_payload["chat"] = None
        with self.assertRaises(LibrarianConfigError):
            _load(api_payload)

    def test_r2_client_preflight_rejects_invalid_or_worker_chat(self) -> None:
        rendered = resolver.render_r2_runtime_configs(_load(_base_payload()))
        invalid_api_chats = (
            {"delivery_mode": "progressive", "unexpected": True},
            {"delivery_mode": "progressive "},
            {"delivery_mode": "disabled"},
            None,
        )
        for chat in invalid_api_chats:
            with self.subTest(chat=chat):
                api_payload = json.loads(rendered["api"])
                api_payload["chat"] = chat
                with self.assertRaises(RuntimeConfigError):
                    parse_broker_client_runtime_config(json.dumps(api_payload))

        worker_payload = json.loads(rendered["summary-worker"])
        worker_payload["chat"] = {"delivery_mode": "buffered"}
        with self.assertRaises(RuntimeConfigError):
            parse_broker_client_runtime_config(json.dumps(worker_payload))


def _base_payload() -> dict[str, object]:
    return json.loads((REPO_ROOT / "config" / "librarian.base.json").read_text(encoding="utf-8"))


def _load(payload: dict[str, object]):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "librarian.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return get_librarian_config(path)


if __name__ == "__main__":
    unittest.main()
