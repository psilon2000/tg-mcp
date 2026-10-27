from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast
import unittest

from tg_mcp.config import Settings
from tg_mcp.telegram_client import TelegramBridge


class _FakeDownloadClient:
    def __init__(self, message: Any | None) -> None:
        self._message = message
        self.last_entity: Any = None
        self.last_ids: Any = None
        self.last_download_message: Any = None
        self.last_output_dir: Any = None

    async def get_messages(self, entity, ids=None):
        self.last_entity = entity
        self.last_ids = ids
        return self._message

    async def download_media(self, message, file=None):
        self.last_download_message = message
        self.last_output_dir = file
        output_path = Path(file) / "report.xlsx"
        output_path.write_bytes(b"xlsx")
        return str(output_path)


class DownloadAttachmentBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_attachment_saves_file_and_returns_metadata(self) -> None:
        bridge = TelegramBridge(_test_settings())
        message = SimpleNamespace(
            id=4321,
            date=datetime(2026, 4, 10, 11, 1, 27, tzinfo=timezone.utc),
            media=object(),
        )
        fake_client = _FakeDownloadClient(message)

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, chat):
            return f"entity:{chat}"

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with TemporaryDirectory() as tmp_dir:
            result = await bridge.download_attachment("example_user", 4321, tmp_dir)

        self.assertEqual(result["chat"], "example_user")
        self.assertEqual(result["message_id"], 4321)
        self.assertEqual(result["date"], "2026-04-10T11:01:27+00:00")
        self.assertEqual(result["file_name"], "report.xlsx")
        self.assertEqual(result["file_size"], 4)
        self.assertEqual(result["attachment_type"], "document")
        self.assertTrue(result["saved_path"].endswith("report.xlsx"))
        self.assertEqual(fake_client.last_entity, "entity:example_user")
        self.assertEqual(fake_client.last_ids, 4321)

    async def test_download_attachment_rejects_message_without_media(self) -> None:
        bridge = TelegramBridge(_test_settings())
        message = SimpleNamespace(id=55, date=datetime.now(timezone.utc), media=None)
        fake_client = _FakeDownloadClient(message)

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        with TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "message_has_no_attachment"):
                await bridge.download_attachment("example_user", 55, tmp_dir)


class ResolveDownloadOutputDirTests(unittest.TestCase):
    def test_accepts_absolute_dir_without_roots(self) -> None:
        import tg_mcp.server as server_module

        with TemporaryDirectory() as tmp_dir:
            original_settings = server_module.settings
            server_module.settings = _test_settings(file_download_roots=())
            try:
                resolved = server_module._resolve_download_output_dir(tmp_dir)
            finally:
                server_module.settings = original_settings

        self.assertEqual(resolved, Path(tmp_dir).resolve())

    def test_rejects_relative_dir_without_roots(self) -> None:
        import tg_mcp.server as server_module

        original_settings = server_module.settings
        server_module.settings = _test_settings(file_download_roots=())
        try:
            with self.assertRaisesRegex(ValueError, "must be absolute"):
                server_module._resolve_download_output_dir("downloads")
        finally:
            server_module.settings = original_settings

    def test_accepts_dir_inside_allowed_roots(self) -> None:
        import tg_mcp.server as server_module

        with TemporaryDirectory() as allowed_dir:
            nested_dir = Path(allowed_dir) / "downloads"
            original_settings = server_module.settings
            server_module.settings = _test_settings(file_download_roots=(Path(allowed_dir).resolve(),))
            try:
                resolved = server_module._resolve_download_output_dir(str(nested_dir))
            finally:
                server_module.settings = original_settings

        self.assertEqual(resolved, nested_dir.resolve())


class DownloadAttachmentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_downloads_via_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def download_attachment(self, chat, message_id, output_dir):
                calls["chat"] = chat
                calls["message_id"] = message_id
                calls["output_dir"] = output_dir
                return {
                    "chat": chat,
                    "message_id": message_id,
                    "date": "2026-04-10T11:01:27+00:00",
                    "saved_path": str(Path(output_dir) / "report.xlsx"),
                    "file_name": "report.xlsx",
                    "file_size": 4,
                    "attachment_type": "document",
                }

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = _test_settings(file_download_roots=())
        server_module.bridge = _BridgeStub()
        try:
            with TemporaryDirectory() as tmp_dir:
                result = await server_module.tg_download_attachment(
                    message_id=4321,
                    output_dir=tmp_dir,
                    chat="example_user",
                )
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["message_id"], 4321)
        self.assertEqual(calls["chat"], "example_user")
        self.assertEqual(calls["message_id"], 4321)
        self.assertEqual(calls["output_dir"], Path(tmp_dir).resolve())


def _test_settings(
    *,
    file_send_roots: tuple[Path, ...] = (),
    file_download_roots: tuple[Path, ...] = (),
) -> Settings:
    return Settings(
        api_id=1,
        api_hash="hash",
        session_path=Path(".session"),
        default_chat=None,
        twofa_password=None,
        write_chat_whitelist=(),
        admin_chat_whitelist=(),
        file_send_roots=file_send_roots,
        file_download_roots=file_download_roots,
    )


if __name__ == "__main__":
    unittest.main()
