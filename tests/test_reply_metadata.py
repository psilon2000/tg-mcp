from types import SimpleNamespace
import unittest

from tg_mcp.telegram_client import _serialize_reply_to


class ReplyMetadataTests(unittest.TestCase):
    def test_no_reply(self):
        self.assertIsNone(_serialize_reply_to(SimpleNamespace()))

    def test_reply_preserves_exact_selected_quote_and_parent(self):
        header = SimpleNamespace(reply_to_msg_id=42, reply_to_top_id=30,
                                 quote_text="Thursday, 15:00", quote_offset=80)
        self.assertEqual(_serialize_reply_to(SimpleNamespace(reply_to=header)), {
            "reply_to_msg_id": 42, "reply_to_top_id": 30,
            "quote_text": "Thursday, 15:00", "quote_offset": 80,
        })

    def test_plain_reply_needs_no_quote(self):
        self.assertEqual(_serialize_reply_to(SimpleNamespace(
            reply_to=SimpleNamespace(reply_to_msg_id=42))), {"reply_to_msg_id": 42})

    def test_non_metadata_is_not_serialized(self):
        header = SimpleNamespace(reply_to_msg_id=None, quote_text=None, unrelated="not exported")
        self.assertIsNone(_serialize_reply_to(SimpleNamespace(reply_to=header)))
