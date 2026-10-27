from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import unittest

from telethon.tl.types import PeerUser

from tg_mcp.config import Settings
from tg_mcp.telegram_client import TelegramBridge, TgFolder


class _FakeClient:
    def __init__(self, dialogs):
        self._dialogs = dialogs

    async def iter_dialogs(self):
        for dialog in self._dialogs:
            yield dialog


class _FakeDialogFilters:
    def __init__(self, filters):
        self.filters = filters


class ListFolderChatsTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_folders_supports_dialog_filters_wrapper(self) -> None:
        bridge = TelegramBridge(_test_settings())

        class _FakeFolderClient:
            async def __call__(self, _request):
                return _FakeDialogFilters(
                    [
                        SimpleNamespace(id=7, title=SimpleNamespace(text="Module")),
                        SimpleNamespace(id=8, title=SimpleNamespace(text="Other")),
                    ]
                )

        folders = await bridge._load_folders(cast(Any, _FakeFolderClient()))

        self.assertEqual(folders, [TgFolder(id=7, name="Module"), TgFolder(id=8, name="Other")])

    async def test_returns_chats_with_extended_fields(self) -> None:
        bridge = TelegramBridge(_test_settings())
        dialogs = [
            SimpleNamespace(
                folder_id=7,
                entity=SimpleNamespace(id=101, username="chat_a"),
                name="Chat A",
                is_channel=True,
                unread_count=5,
                pinned=True,
                message=SimpleNamespace(date=datetime(2026, 3, 6, 9, 0, tzinfo=timezone.utc)),
            ),
            SimpleNamespace(
                folder_id=8,
                entity=SimpleNamespace(id=202, username="chat_b"),
                name="Chat B",
                is_channel=False,
                unread_count=0,
                pinned=False,
                message=None,
            ),
        ]
        fake_client = _FakeClient(dialogs)

        async def fake_ensure_connected():
            return fake_client

        async def fake_load_folders(_client):
            return [TgFolder(id=7, name="Module")]

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._load_folders = fake_load_folders

        result = await bridge.list_folder_chats(folder="mod", limit=10)

        self.assertEqual(result["folder"], "Module")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["chats"][0]["chat_id"], 101)
        self.assertEqual(result["chats"][0]["username"], "chat_a")
        self.assertEqual(result["chats"][0]["last_message_date"], "2026-03-06T09:00:00+00:00")

    async def test_empty_folder_returns_ok_payload(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient(dialogs=[])

        async def fake_ensure_connected():
            return fake_client

        async def fake_load_folders(_client):
            return [TgFolder(id=7, name="Module")]

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._load_folders = fake_load_folders

        result = await bridge.list_folder_chats(folder="module", limit=50)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["chats"], [])

    async def test_invalid_limit(self) -> None:
        bridge = TelegramBridge(_test_settings())
        with self.assertRaisesRegex(ValueError, "invalid_limit"):
            await bridge.list_folder_chats(folder="Module", limit=0)

    async def test_missing_username_and_last_date(self) -> None:
        bridge = TelegramBridge(_test_settings())
        dialogs = [
            SimpleNamespace(
                folder_id=7,
                entity=SimpleNamespace(id=303),
                name="No Meta",
                is_channel=False,
                unread_count=0,
                pinned=False,
                message=SimpleNamespace(date=None),
            )
        ]
        fake_client = _FakeClient(dialogs)

        async def fake_ensure_connected():
            return fake_client

        async def fake_load_folders(_client):
            return [TgFolder(id=7, name="Module")]

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._load_folders = fake_load_folders

        result = await bridge.list_folder_chats(folder="module", limit=10)
        self.assertIsNone(result["chats"][0]["username"])
        self.assertEqual(result["chats"][0]["last_message_date"], "")

    async def test_matches_folder_by_peer_ids_when_dialog_folder_id_missing(self) -> None:
        bridge = TelegramBridge(_test_settings())
        dialogs = [
            SimpleNamespace(
                folder_id=None,
                entity=PeerUser(user_id=777),
                name="Peer Matched",
                is_channel=False,
                unread_count=2,
                pinned=False,
                message=None,
            )
        ]
        fake_client = _FakeClient(dialogs)

        async def fake_ensure_connected():
            return fake_client

        async def fake_load_folders(_client):
            return [TgFolder(id=7, name="Module", peer_ids=frozenset({777}))]

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._load_folders = fake_load_folders

        result = await bridge.list_folder_chats(folder="module", limit=10)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["chats"][0]["chat_id"], 777)


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
