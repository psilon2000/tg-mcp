from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import unittest
from unittest.mock import patch

from telethon.tl.functions.channels import EditBannedRequest, InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest, DeleteChatUserRequest

from tg_mcp.config import Settings, load_settings
from tg_mcp.telegram_client import TelegramBridge


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


class ConfigTests(unittest.TestCase):
    def test_load_settings_reads_admin_chat_whitelist(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TG_API_ID": "1",
                "TG_API_HASH": "hash",
                "TG_ADMIN_CHAT_WHITELIST": "ops,@group,123",
            },
            clear=False,
        ):
            settings = load_settings()

        self.assertEqual(settings.admin_chat_whitelist, ("ops", "@group", "123"))


class _FakeBasicGroupClient:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def __call__(self, request):
        self.requests.append(request)
        return SimpleNamespace()

    async def get_input_entity(self, value):
        return f"input:{value}"


Chat = type("Chat", (), {})
Channel = type("Channel", (), {})


def _chat_entity(chat_id: int, title: str):
    entity = Chat()
    entity.id = chat_id
    entity.title = title
    return entity


def _megagroup_entity(chat_id: int, title: str):
    entity = Channel()
    entity.id = chat_id
    entity.title = title
    entity.megagroup = True
    return entity


def _channel_entity(chat_id: int, title: str):
    entity = Channel()
    entity.id = chat_id
    entity.title = title
    entity.megagroup = False
    return entity


class GroupMemberBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_member_to_basic_group(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeBasicGroupClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return _chat_entity(77, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.add_group_member("ops", "@alice")

        self.assertEqual(result, {"chat": "ops", "member": "@alice", "action": "add"})
        self.assertIsInstance(fake_client.requests[0], AddChatUserRequest)

    async def test_remove_member_from_basic_group(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeBasicGroupClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return _chat_entity(77, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.remove_group_member("ops", "42")

        self.assertEqual(result, {"chat": "ops", "member": "42", "action": "remove"})
        self.assertIsInstance(fake_client.requests[0], DeleteChatUserRequest)

    async def test_add_member_to_megagroup(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeBasicGroupClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return _megagroup_entity(88, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        await bridge.add_group_member("ops", "@alice")

        self.assertIsInstance(fake_client.requests[0], InviteToChannelRequest)

    async def test_remove_member_from_megagroup_uses_ban_unban(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeBasicGroupClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return _megagroup_entity(88, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        await bridge.remove_group_member("ops", "@alice")

        self.assertEqual(len(fake_client.requests), 2)
        self.assertIsInstance(fake_client.requests[0], EditBannedRequest)
        self.assertIsInstance(fake_client.requests[1], EditBannedRequest)

    async def test_rejects_unsupported_chat_type(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeBasicGroupClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return _channel_entity(99, "Broadcast")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with self.assertRaisesRegex(ValueError, "unsupported_chat_type"):
            await bridge.add_group_member("broadcast", "@alice")

    async def test_rejects_empty_member(self) -> None:
        bridge = TelegramBridge(_test_settings())

        with self.assertRaisesRegex(ValueError, "member is required"):
            await bridge.add_group_member("ops", " ")

    async def test_member_not_found(self) -> None:
        bridge = TelegramBridge(_test_settings())

        class _Client:
            async def get_input_entity(self, value):
                raise RuntimeError("boom")

        async def fake_ensure_connected():
            return _Client()

        async def fake_resolve_entity(_client, _chat):
            return _chat_entity(77, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with self.assertRaisesRegex(ValueError, "member_not_found"):
            await bridge.add_group_member("ops", "@missing")

    async def test_propagates_member_already_exists_error(self) -> None:
        bridge = TelegramBridge(_test_settings())

        class _Client(_FakeBasicGroupClient):
            async def __call__(self, request):
                raise RuntimeError("USER_ALREADY_PARTICIPANT")

        async def fake_ensure_connected():
            return _Client()

        async def fake_resolve_entity(_client, _chat):
            return _chat_entity(77, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with self.assertRaisesRegex(RuntimeError, "USER_ALREADY_PARTICIPANT"):
            await bridge.add_group_member("ops", "@alice")

    async def test_propagates_member_already_missing_error(self) -> None:
        bridge = TelegramBridge(_test_settings())

        class _Client(_FakeBasicGroupClient):
            async def __call__(self, request):
                raise RuntimeError("USER_NOT_PARTICIPANT")

        async def fake_ensure_connected():
            return _Client()

        async def fake_resolve_entity(_client, _chat):
            return _chat_entity(77, "Ops")

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with self.assertRaisesRegex(RuntimeError, "USER_NOT_PARTICIPANT"):
            await bridge.remove_group_member("ops", "@alice")


class GroupMemberToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_tool_requires_chat(self) -> None:
        import tg_mcp.server as server_module

        with self.assertRaisesRegex(ValueError, "chat is required"):
            await server_module.tg_add_group_member(chat=" ", member="@alice", confirm=True)

    async def test_add_tool_requires_member(self) -> None:
        import tg_mcp.server as server_module

        with self.assertRaisesRegex(ValueError, "member is required"):
            await server_module.tg_add_group_member(chat="ops", member=" ", confirm=True)

    async def test_add_tool_requires_confirm(self) -> None:
        import tg_mcp.server as server_module

        original_settings = server_module.settings
        server_module.settings = _test_settings(admin_chat_whitelist=("ops",))
        try:
            with self.assertRaisesRegex(ValueError, "confirm=true"):
                await server_module.tg_add_group_member(chat="ops", member="@alice", confirm=False)
        finally:
            server_module.settings = original_settings

    async def test_add_tool_rejects_empty_admin_whitelist(self) -> None:
        import tg_mcp.server as server_module

        original_settings = server_module.settings
        server_module.settings = _test_settings(admin_chat_whitelist=())
        try:
            with self.assertRaisesRegex(ValueError, "TG_ADMIN_CHAT_WHITELIST"):
                await server_module.tg_add_group_member(chat="ops", member="@alice", confirm=True)
        finally:
            server_module.settings = original_settings

    async def test_add_tool_rejects_chat_outside_admin_whitelist(self) -> None:
        import tg_mcp.server as server_module

        original_settings = server_module.settings
        server_module.settings = _test_settings(admin_chat_whitelist=("ops",))
        try:
            with self.assertRaisesRegex(ValueError, "admin whitelist"):
                await server_module.tg_add_group_member(chat="other", member="@alice", confirm=True)
        finally:
            server_module.settings = original_settings

    async def test_add_tool_uses_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def add_group_member(self, chat, member):
                calls["chat"] = chat
                calls["member"] = member
                return {"chat": chat, "member": member, "action": "add"}

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = _test_settings(admin_chat_whitelist=("ops",))
        server_module.bridge = _BridgeStub()
        try:
            result = await server_module.tg_add_group_member(chat="ops", member=" @alice ", confirm=True)
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result, {"status": "ok", "chat": "ops", "member": "@alice", "action": "add"})
        self.assertEqual(calls, {"chat": "ops", "member": "@alice"})

    async def test_remove_tool_uses_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def remove_group_member(self, chat, member):
                calls["chat"] = chat
                calls["member"] = member
                return {"chat": chat, "member": member, "action": "remove"}

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = _test_settings(admin_chat_whitelist=("ops",))
        server_module.bridge = _BridgeStub()
        try:
            result = await server_module.tg_remove_group_member(chat="ops", member="42", confirm=True)
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result, {"status": "ok", "chat": "ops", "member": "42", "action": "remove"})
        self.assertEqual(calls, {"chat": "ops", "member": "42"})


def _test_settings(
    write_chat_whitelist: tuple[str, ...] = (),
    admin_chat_whitelist: tuple[str, ...] = (),
) -> Settings:
    return Settings(
        api_id=1,
        api_hash="hash",
        session_path=Path(".session"),
        default_chat=None,
        twofa_password=None,
        write_chat_whitelist=write_chat_whitelist,
        admin_chat_whitelist=admin_chat_whitelist,
        file_send_roots=(),
    )


if __name__ == "__main__":
    unittest.main()
