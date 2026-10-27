from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast
import unittest

from tg_mcp.config import Settings
from tg_mcp.telegram_client import TelegramBridge


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


class _FakeFileClient:
    def __init__(self) -> None:
        self.last_entity: Any = None
        self.last_file: Any = None
        self.last_caption: Any = None
        self.response_messages = [
            SimpleNamespace(id=77, date=datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc))
        ]

    async def send_file(self, entity, file, caption=None):
        self.last_entity = entity
        self.last_file = file
        self.last_caption = caption
        if isinstance(file, list):
            return self.response_messages
        return self.response_messages[0]


class SendFileBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_file_returns_metadata(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeFileClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, chat):
            return f"entity:{chat}"

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "report.txt"
            file_path.write_text("hello")

            result = await bridge.send_file("me", file_path, caption="status")

        self.assertEqual(result["chat"], "me")
        self.assertEqual(result["message_id"], 77)
        self.assertEqual(result["date"], "2026-03-16T10:30:00+00:00")
        self.assertEqual(result["file_name"], "report.txt")
        self.assertEqual(result["file_size"], 5)
        self.assertEqual(result["attachment_type"], "document")
        self.assertEqual(result["caption"], "status")
        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(len(result["attachments"]), 1)
        self.assertEqual(fake_client.last_entity, "entity:me")
        self.assertEqual(fake_client.last_caption, "status")

    async def test_send_file_supports_multiple_attachments(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeFileClient()
        fake_client.response_messages = [
            SimpleNamespace(id=77, date=datetime(2026, 3, 16, 10, 30, tzinfo=timezone.utc)),
            SimpleNamespace(id=78, date=datetime(2026, 3, 16, 10, 31, tzinfo=timezone.utc)),
        ]

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, chat):
            return f"entity:{chat}"

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with TemporaryDirectory() as tmp_dir:
            first_path = Path(tmp_dir) / "photo.png"
            second_path = Path(tmp_dir) / "report.txt"
            first_path.write_bytes(b"png")
            second_path.write_text("hello")

            result = await bridge.send_file("me", [first_path, second_path], caption="bundle")

        self.assertEqual(result["attachment_count"], 2)
        self.assertEqual(result["caption"], "bundle")
        self.assertEqual(len(result["attachments"]), 2)
        self.assertEqual(result["attachments"][0]["attachment_type"], "photo")
        self.assertEqual(result["attachments"][1]["attachment_type"], "document")
        last_file = fake_client.last_file
        self.assertIsInstance(last_file, list)
        if not isinstance(last_file, list):
            self.fail("expected list of file paths")
        self.assertEqual([Path(item).name for item in last_file], ["photo.png", "report.txt"])

    async def test_send_file_rejects_missing_path(self) -> None:
        bridge = TelegramBridge(_test_settings())
        with self.assertRaisesRegex(ValueError, "file_not_found"):
            await bridge.send_file("me", "/tmp/definitely-missing-file")

    async def test_send_file_rejects_directory(self) -> None:
        bridge = TelegramBridge(_test_settings())
        with TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "not_a_file"):
                await bridge.send_file("me", tmp_dir)


class ResolveSendFilePathTests(unittest.TestCase):
    def test_accepts_absolute_path_without_roots(self) -> None:
        import tg_mcp.server as server_module

        with TemporaryDirectory() as tmp_dir:
            original_settings = server_module.settings
            server_module.settings = _test_settings(file_send_roots=())
            try:
                file_path = Path(tmp_dir) / "report.txt"
                resolved = server_module._resolve_send_file_path(str(file_path))
            finally:
                server_module.settings = original_settings

        self.assertEqual(resolved, file_path.resolve())

    def test_accepts_path_inside_allowed_root(self) -> None:
        import tg_mcp.server as server_module

        with TemporaryDirectory() as allowed_dir:
            original_settings = server_module.settings
            server_module.settings = _test_settings(file_send_roots=(Path(allowed_dir).resolve(),))
            try:
                file_path = Path(allowed_dir) / "report.txt"
                resolved = server_module._resolve_send_file_path(str(file_path))
            finally:
                server_module.settings = original_settings

        self.assertEqual(resolved, file_path.resolve())

    def test_rejects_relative_path_without_roots(self) -> None:
        import tg_mcp.server as server_module

        original_settings = server_module.settings
        server_module.settings = _test_settings(file_send_roots=())
        try:
            with self.assertRaisesRegex(ValueError, "must be absolute"):
                server_module._resolve_send_file_path("report.txt")
        finally:
            server_module.settings = original_settings

    def test_rejects_path_outside_allowed_roots(self) -> None:
        import tg_mcp.server as server_module

        with TemporaryDirectory() as allowed_dir, TemporaryDirectory() as blocked_dir:
            original_settings = server_module.settings
            server_module.settings = _test_settings(file_send_roots=(Path(allowed_dir).resolve(),))
            try:
                blocked_file = Path(blocked_dir) / "secret.txt"
                with self.assertRaisesRegex(ValueError, "outside allowed roots"):
                    server_module._resolve_send_file_path(str(blocked_file))
            finally:
                server_module.settings = original_settings

    def test_resolves_multiple_paths(self) -> None:
        import tg_mcp.server as server_module

        with TemporaryDirectory() as allowed_dir:
            original_settings = server_module.settings
            server_module.settings = _test_settings(file_send_roots=(Path(allowed_dir).resolve(),))
            try:
                first_path = Path(allowed_dir) / "a.txt"
                second_path = Path(allowed_dir) / "b.txt"
                resolved = server_module._resolve_send_file_paths(
                    file_paths=[str(first_path), str(second_path)]
                )
            finally:
                server_module.settings = original_settings

        self.assertEqual(resolved, [first_path.resolve(), second_path.resolve()])


class SendFileToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_confirm_before_sending(self) -> None:
        import tg_mcp.server as server_module

        original_settings = server_module.settings
        server_module.settings = _test_settings(write_chat_whitelist=("me",))
        try:
            with TemporaryDirectory() as tmp_dir:
                file_path = Path(tmp_dir) / "report.txt"
                file_path.write_text("hello")
                with self.assertRaisesRegex(ValueError, "confirm=true"):
                    await server_module.tg_send_file(str(file_path), chat="me", confirm=False)
        finally:
            server_module.settings = original_settings

    async def test_sends_file_via_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def send_file(self, chat, file_path, caption=None):
                calls["chat"] = chat
                calls["file_path"] = file_path
                calls["caption"] = caption
                return {
                    "chat": chat,
                    "caption": caption,
                    "attachment_count": 1,
                    "attachments": [
                        {
                            "message_id": 99,
                            "date": "2026-03-16T11:00:00+00:00",
                            "file_name": Path(file_path[0]).name if isinstance(file_path, list) else Path(file_path).name,
                            "file_size": Path(file_path[0]).stat().st_size if isinstance(file_path, list) else Path(file_path).stat().st_size,
                            "attachment_type": "document",
                        }
                    ],
                    "message_id": 99,
                    "date": "2026-03-16T11:00:00+00:00",
                    "file_name": Path(file_path[0]).name if isinstance(file_path, list) else Path(file_path).name,
                    "file_size": Path(file_path[0]).stat().st_size if isinstance(file_path, list) else Path(file_path).stat().st_size,
                    "attachment_type": "document",
                }

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = _test_settings(write_chat_whitelist=("me",))
        server_module.bridge = _BridgeStub()
        try:
            with TemporaryDirectory() as tmp_dir:
                file_path = Path(tmp_dir) / "report.txt"
                file_path.write_text("hello")
                result = await server_module.tg_send_file(
                    str(file_path),
                    caption="status",
                    chat="me",
                    confirm=True,
                )
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["message_id"], 99)
        self.assertEqual(calls["chat"], "me")
        self.assertEqual(calls["caption"], "status")
        sent_paths = cast(list[Path], calls["file_path"])
        self.assertEqual(len(sent_paths), 1)
        self.assertEqual(Path(sent_paths[0]).name, "report.txt")

    async def test_accepts_file_paths_list(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def send_file(self, chat, file_path, caption=None):
                calls["chat"] = chat
                calls["file_path"] = file_path
                calls["caption"] = caption
                return {
                    "chat": chat,
                    "caption": caption,
                    "attachment_count": 2,
                    "attachments": [
                        {
                            "message_id": 11,
                            "date": "2026-03-16T11:00:00+00:00",
                            "file_name": Path(file_path[0]).name,
                            "file_size": Path(file_path[0]).stat().st_size,
                            "attachment_type": "document",
                        },
                        {
                            "message_id": 12,
                            "date": "2026-03-16T11:00:01+00:00",
                            "file_name": Path(file_path[1]).name,
                            "file_size": Path(file_path[1]).stat().st_size,
                            "attachment_type": "photo",
                        },
                    ],
                    "message_id": 11,
                    "date": "2026-03-16T11:00:00+00:00",
                    "file_name": Path(file_path[0]).name,
                    "file_size": Path(file_path[0]).stat().st_size,
                    "attachment_type": "document",
                }

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = _test_settings(write_chat_whitelist=("me",))
        server_module.bridge = _BridgeStub()
        try:
            with TemporaryDirectory() as tmp_dir:
                first_path = Path(tmp_dir) / "report.txt"
                second_path = Path(tmp_dir) / "photo.png"
                first_path.write_text("hello")
                second_path.write_bytes(b"png")
                result = await server_module.tg_send_file(
                    file_paths=[str(first_path), str(second_path)],
                    caption="bundle",
                    chat="me",
                    confirm=True,
                )
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["attachment_count"], 2)
        sent_paths = cast(list[Path], calls["file_path"])
        self.assertEqual(len(sent_paths), 2)
        self.assertEqual(calls["caption"], "bundle")


class SendMessageBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_supports_reply_to(self) -> None:
        bridge = TelegramBridge(_test_settings())

        class _FakeMessageClient:
            def __init__(self) -> None:
                self.last_entity: Any = None
                self.last_text: Any = None
                self.last_kwargs: dict[str, Any] | None = None

            async def send_message(self, entity, text, **kwargs):
                self.last_entity = entity
                self.last_text = text
                self.last_kwargs = kwargs
                return SimpleNamespace(id=123, date=datetime(2026, 3, 26, 8, 50, tzinfo=timezone.utc))

        fake_client = _FakeMessageClient()

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, chat):
            return f"entity:{chat}"

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.send_message("me", "hello", reply_to_message_id=42)

        self.assertEqual(result["chat"], "me")
        self.assertEqual(result["message_id"], 123)
        self.assertEqual(fake_client.last_entity, "entity:me")
        self.assertEqual(fake_client.last_text, "hello")
        self.assertEqual(fake_client.last_kwargs, {"reply_to": 42})


class SendMessageToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_reply_to_via_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def send_message(self, chat, text, reply_to_message_id=None):
                calls["chat"] = chat
                calls["text"] = text
                calls["reply_to_message_id"] = reply_to_message_id
                return {
                    "chat": chat,
                    "message_id": 321,
                    "date": "2026-03-26T08:51:00+00:00",
                }

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = _test_settings(write_chat_whitelist=("me",))
        server_module.bridge = _BridgeStub()
        try:
            result = await server_module.tg_send_message(
                "hello",
                chat="me",
                reply_to_message_id=42,
                confirm=True,
            )
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["message_id"], 321)
        self.assertEqual(calls["chat"], "me")
        self.assertEqual(calls["text"], "hello")
        self.assertEqual(calls["reply_to_message_id"], 42)


def _test_settings(
    file_send_roots: tuple[Path, ...] = (),
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
        file_send_roots=file_send_roots,
        file_download_roots=(),
    )


if __name__ == "__main__":
    unittest.main()
