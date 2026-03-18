from __future__ import annotations

import os
import unittest


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


@unittest.skipUnless(os.getenv("TG_RUN_REAL_E2E") == "1", "set TG_RUN_REAL_E2E=1 for live Telegram tests")
class GroupMemberAdminRealE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_live_add_remove_member_flow(self) -> None:
        import tg_mcp.server as server_module

        chat = os.getenv("TG_REAL_ADMIN_TEST_CHAT", "").strip()
        member = os.getenv("TG_REAL_ADMIN_TEST_MEMBER", "").strip()
        if not chat or not member:
            self.skipTest("set TG_REAL_ADMIN_TEST_CHAT and TG_REAL_ADMIN_TEST_MEMBER for live member-admin tests")

        result_add = await server_module.tg_add_group_member(chat=chat, member=member, confirm=True)
        self.assertEqual(result_add["status"], "ok")
        self.assertEqual(result_add["chat"], chat)
        self.assertEqual(result_add["member"], member)
        self.assertEqual(result_add["action"], "add")

        result_remove = await server_module.tg_remove_group_member(chat=chat, member=member, confirm=True)
        self.assertEqual(result_remove["status"], "ok")
        self.assertEqual(result_remove["chat"], chat)
        self.assertEqual(result_remove["member"], member)
        self.assertEqual(result_remove["action"], "remove")


if __name__ == "__main__":
    unittest.main()
