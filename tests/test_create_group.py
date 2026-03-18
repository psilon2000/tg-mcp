from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import unittest

from telethon.tl.functions.messages import CreateChatRequest

from tg_mcp.config import Settings
from tg_mcp.telegram_client import TelegramBridge


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


class _FakeCreateGroupClient:
    def __init__(self) -> None:
        self.last_request: Any = None
        self.response: Any = SimpleNamespace(
            updates=SimpleNamespace(
                chats=[SimpleNamespace(id=321, title="Launch Squad")]
            )
        )

    async def __call__(self, request):
        self.last_request = request
        return self.response


class CreateGroupBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_group_returns_minimal_payload(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeCreateGroupClient()

        async def fake_ensure_connected():
            return fake_client

        cast(Any, bridge).ensure_connected = fake_ensure_connected

        result = await bridge.create_group("  Launch Squad  ")

        self.assertEqual(result, {"chat_id": 321, "title": "Launch Squad"})
        self.assertIsInstance(fake_client.last_request, CreateChatRequest)
        self.assertEqual(fake_client.last_request.title, "Launch Squad")
        self.assertEqual(fake_client.last_request.users, [])

    async def test_create_group_rejects_empty_title(self) -> None:
        bridge = TelegramBridge(_test_settings())

        with self.assertRaisesRegex(ValueError, "invalid_title"):
            await bridge.create_group("")

    async def test_create_group_rejects_whitespace_title(self) -> None:
        bridge = TelegramBridge(_test_settings())

        with self.assertRaisesRegex(ValueError, "invalid_title"):
            await bridge.create_group("   ")

    async def test_create_group_propagates_client_error(self) -> None:
        bridge = TelegramBridge(_test_settings())

        class _FailingClient:
            async def __call__(self, request):
                raise RuntimeError("telegram_failure")

        async def fake_ensure_connected():
            return _FailingClient()

        cast(Any, bridge).ensure_connected = fake_ensure_connected

        with self.assertRaisesRegex(RuntimeError, "telegram_failure"):
            await bridge.create_group("Launch Squad")

    async def test_create_group_passes_through_long_title(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeCreateGroupClient()
        long_title = "x" * 300

        async def fake_ensure_connected():
            return fake_client

        cast(Any, bridge).ensure_connected = fake_ensure_connected

        await bridge.create_group(long_title)

        self.assertEqual(fake_client.last_request.title, long_title)


class CreateGroupToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_creates_group_via_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def create_group(self, title):
                calls["title"] = title
                return {
                    "chat_id": 321,
                    "title": title.strip(),
                }

        original_bridge = server_module.bridge
        server_module.bridge = _BridgeStub()
        try:
            result = await server_module.tg_create_group("  Launch Squad  ")
        finally:
            server_module.bridge = original_bridge

        self.assertEqual(result, {"status": "ok", "chat_id": 321, "title": "Launch Squad"})
        self.assertEqual(calls["title"], "  Launch Squad  ")


def _test_settings() -> Settings:
    return Settings(
        api_id=1,
        api_hash="hash",
        session_path=Path(".session"),
        default_chat=None,
        twofa_password=None,
        write_chat_whitelist=(),
        admin_chat_whitelist=(),
        file_send_roots=(),
    )


if __name__ == "__main__":
    unittest.main()
