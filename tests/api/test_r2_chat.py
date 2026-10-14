"""Lifecycle tests for the inactive R2 API-chat composition seam."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from librarian_api.r2_chat import R2ApiChatCaller


class R2ApiChatCallerTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_reuses_ready_client_for_all_chat_operations_and_closes_it(self) -> None:
        client = _Client()
        with patch("librarian_api.r2_chat.open_r2_client", AsyncMock(return_value=client)) as open_client:
            caller = await R2ApiChatCaller.open(model_id="gpt-5.6-sol")

        open_client.assert_awaited_once_with(expected_principal="api")
        self.assertIs(caller.operations.client, client)
        self.assertEqual(caller.operations.model_id, "gpt-5.6-sol")
        await caller.close()
        self.assertTrue(client.closed)

    async def test_invalid_model_is_rejected_before_opening_a_channel(self) -> None:
        with (
            patch("librarian_api.r2_chat.open_r2_client", AsyncMock()) as open_client,
            self.assertRaisesRegex(ValueError, "require a model ID"),
        ):
            await R2ApiChatCaller.open(model_id=" ")

        open_client.assert_not_awaited()


class _Client:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True
