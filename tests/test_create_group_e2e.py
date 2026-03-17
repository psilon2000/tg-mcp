from __future__ import annotations

import os
import time
import unittest


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


@unittest.skipUnless(os.getenv("TG_RUN_REAL_E2E") == "1", "set TG_RUN_REAL_E2E=1 for live Telegram tests")
class CreateGroupRealE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_creates_group_with_live_telegram_session(self) -> None:
        import tg_mcp.server as server_module

        title = f"tg-mcp-e2e-{int(time.time())}"
        result = await server_module.tg_create_group(title)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["title"], title)
        self.assertIsInstance(result["chat_id"], int)
        self.assertNotEqual(result["chat_id"], 0)


if __name__ == "__main__":
    unittest.main()
