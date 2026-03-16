from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


class SendFileE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_sends_multiple_files_with_default_chat(self) -> None:
        import tg_mcp.server as server_module
        from tg_mcp.config import Settings

        calls: dict[str, object] = {}

        class _BridgeStub:
            async def send_file(self, chat, file_path, caption=None):
                calls["chat"] = chat
                calls["file_path"] = file_path
                calls["caption"] = caption
                attachments = []
                for index, path in enumerate(file_path, start=1):
                    current = Path(path)
                    attachments.append(
                        {
                            "message_id": index,
                            "date": f"2026-03-16T11:00:0{index}+00:00",
                            "file_name": current.name,
                            "file_size": current.stat().st_size,
                            "attachment_type": "photo" if current.suffix == ".png" else "document",
                        }
                    )
                first = attachments[0]
                return {
                    "chat": chat,
                    "caption": caption,
                    "attachment_count": len(attachments),
                    "attachments": attachments,
                    **first,
                }

        original_settings = server_module.settings
        original_bridge = server_module.bridge
        server_module.settings = Settings(
            api_id=1,
            api_hash="hash",
            session_path=Path(".session"),
            default_chat="me",
            twofa_password=None,
            write_chat_whitelist=("me",),
            file_send_roots=(),
        )
        server_module.bridge = _BridgeStub()

        try:
            with TemporaryDirectory() as tmp_dir:
                first_path = Path(tmp_dir) / "doc.txt"
                second_path = Path(tmp_dir) / "image.png"
                first_path.write_text("hello")
                second_path.write_bytes(b"png")

                result = await server_module.tg_send_file(
                    file_paths=[str(first_path), str(second_path)],
                    caption="release bundle",
                    confirm=True,
                )
        finally:
            server_module.settings = original_settings
            server_module.bridge = original_bridge

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["chat"], "me")
        self.assertEqual(result["caption"], "release bundle")
        self.assertEqual(result["attachment_count"], 2)
        self.assertEqual(result["attachments"][0]["file_name"], "doc.txt")
        self.assertEqual(result["attachments"][1]["attachment_type"], "photo")
        self.assertEqual(calls["chat"], "me")


if __name__ == "__main__":
    unittest.main()
