from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import unittest

from telethon.tl.types import MessageFwdHeader, MessagePeerReaction, PeerUser, ReactionCount, ReactionCustomEmoji, ReactionEmoji, User

from tg_mcp.config import Settings
from tg_mcp.telegram_client import TelegramBridge


os.environ.setdefault("TG_API_ID", "1")
os.environ.setdefault("TG_API_HASH", "hash")


class _FakeClient:
    def __init__(self, messages):
        self._messages = messages
        self.iter_kwargs = None
        self.get_messages_ids = None

    async def iter_messages(self, _entity, **kwargs):
        self.iter_kwargs = kwargs
        limit = kwargs.get("limit", 20)
        for message in self._messages[:limit]:
            yield message

    async def get_messages(self, _entity, ids):
        self.get_messages_ids = ids
        if isinstance(ids, list):
            return [self._message_by_id(message_id) for message_id in ids]
        return self._message_by_id(ids)

    def _message_by_id(self, message_id):
        for message in self._messages:
            if message.id == message_id:
                return message
        return None


class ReadMessagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_includes_forwarded_source_metadata(self) -> None:
        bridge = TelegramBridge(_test_settings())
        forwarded_at = datetime(2026, 7, 16, 14, 44, 42, tzinfo=timezone.utc)
        fake_client = _FakeClient(
            [
                SimpleNamespace(
                    id=287974,
                    chat_id=6554269133,
                    sender_id=6554269133,
                    date=datetime(2026, 7, 22, 10, 43, 35, tzinfo=timezone.utc),
                    message="Forwarded text",
                    media=None,
                    reactions=None,
                    fwd_from=MessageFwdHeader(
                        date=forwarded_at,
                        from_id=PeerUser(user_id=44115459),
                    ),
                    forward=SimpleNamespace(
                        sender_id=44115459,
                        sender=User(id=44115459, first_name="Alan", last_name="Badjiti"),
                    ),
                )
            ]
        )

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.read_messages("test", limit=5)

        self.assertEqual(result[0].forwarded_from, {
            "sender_id": 44115459,
            "sender_name": "Alan Badjiti",
            "date_iso": "2026-07-16T14:44:42+00:00",
        })

    async def test_includes_reaction_counts_and_recent_reactions(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient(
            [
                SimpleNamespace(
                    id=10,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 3, 18, 11, 48, 59, tzinfo=timezone.utc),
                    message="Thanks",
                    media=None,
                    reactions=SimpleNamespace(
                        results=[
                            ReactionCount(reaction=ReactionEmoji(emoticon="🙏"), count=1, chosen_order=0),
                            ReactionCount(reaction=ReactionCustomEmoji(document_id=42), count=2, chosen_order=None),
                        ],
                        recent_reactions=[
                            MessagePeerReaction(
                                peer_id=PeerUser(user_id=188751178),
                                date=datetime(2026, 3, 18, 11, 49, 3, tzinfo=timezone.utc),
                                reaction=ReactionEmoji(emoticon="🙏"),
                                big=False,
                                unread=False,
                                my=True,
                            )
                        ],
                    ),
                )
            ]
        )

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.read_messages("test", limit=5)

        self.assertEqual(result[0].reactions, [
            {"reaction": "🙏", "count": 1, "chosen_order": 0},
            {"reaction": "42", "count": 2, "chosen_order": None},
        ])
        self.assertEqual(result[0].recent_reactions, [
            {
                "peer_id": 188751178,
                "date_iso": "2026-03-18T11:49:03+00:00",
                "reaction": "🙏",
                "big": False,
                "unread": False,
                "my": True,
            }
        ])
        self.assertEqual(result[0].attachment_count, 0)
        self.assertEqual(result[0].attachments, [])
        self.assertIsNone(result[0].forwarded_from)

    async def test_includes_attachment_metadata_when_message_has_media(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient(
            [
                SimpleNamespace(
                    id=12,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 3, 18, 12, 1, 0, tzinfo=timezone.utc),
                    message="See screenshot",
                    media=object(),
                    file=SimpleNamespace(name="screen.png", size=2048, mime_type="image/png"),
                    reactions=None,
                )
            ]
        )

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.read_messages("test", limit=5)

        self.assertEqual(result[0].attachment_count, 1)
        self.assertEqual(result[0].attachments, [
            {
                "message_id": 12,
                "date": "2026-03-18T12:01:00+00:00",
                "attachment_type": "photo",
                "file_name": "screen.png",
                "file_size": 2048,
                "mime_type": "image/png",
            }
        ])

    async def test_messages_without_reactions_return_empty_lists(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient(
            [
                SimpleNamespace(
                    id=11,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc),
                    message="No reactions",
                    media=None,
                    reactions=None,
                )
            ]
        )

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.read_messages("test", limit=5)

        self.assertEqual(result[0].reactions, [])
        self.assertEqual(result[0].recent_reactions, [])
        self.assertEqual(result[0].attachment_count, 0)
        self.assertEqual(result[0].attachments, [])

    async def test_reads_specific_messages_by_id(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient(
            [
                SimpleNamespace(
                    id=41,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 1, 15, 17, 10, 0, tzinfo=timezone.utc),
                    message="first",
                    media=None,
                    reactions=None,
                ),
                SimpleNamespace(
                    id=42,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 1, 15, 17, 11, 0, tzinfo=timezone.utc),
                    message="second",
                    media=None,
                    reactions=None,
                ),
            ]
        )

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.read_messages("test", message_ids=[42, 41, 42])

        self.assertEqual(fake_client.get_messages_ids, [42, 41])
        self.assertEqual([message.id for message in result], [41, 42])

    async def test_reads_messages_from_date_window(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient(
            [
                SimpleNamespace(
                    id=3,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 1, 15, 17, 20, 0, tzinfo=timezone.utc),
                    message="inside upper",
                    media=None,
                    reactions=None,
                ),
                SimpleNamespace(
                    id=2,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 1, 15, 17, 10, 0, tzinfo=timezone.utc),
                    message="inside lower",
                    media=None,
                    reactions=None,
                ),
                SimpleNamespace(
                    id=1,
                    chat_id=777,
                    sender_id=123,
                    date=datetime(2026, 1, 15, 16, 50, 0, tzinfo=timezone.utc),
                    message="too old",
                    media=None,
                    reactions=None,
                ),
            ]
        )

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        result = await bridge.read_messages(
            "test",
            limit=10,
            since_iso="2026-01-15T17:00:00+00:00",
            until_iso="2026-01-15T17:30:00+00:00",
        )

        self.assertEqual(fake_client.iter_kwargs["offset_date"], datetime(2026, 1, 15, 17, 30, 0, tzinfo=timezone.utc))
        self.assertEqual([message.id for message in result], [2, 3])

    async def test_passes_offset_id_to_iter_messages(self) -> None:
        bridge = TelegramBridge(_test_settings())
        fake_client = _FakeClient([])

        async def fake_ensure_connected():
            return fake_client

        async def fake_resolve_entity(_client, _chat):
            return object()

        cast(Any, bridge).ensure_connected = fake_ensure_connected
        cast(Any, bridge)._resolve_entity = fake_resolve_entity

        await bridge.read_messages("test", limit=5, offset_id=1201)

        self.assertEqual(fake_client.iter_kwargs["offset_id"], 1201)

    async def test_tool_passes_window_offset_and_ids_to_bridge(self) -> None:
        import tg_mcp.server as server_module

        calls: dict[str, Any] = {}

        class _BridgeStub:
            async def read_messages(
                self,
                chat,
                limit=20,
                since_iso=None,
                until_iso=None,
                offset_id=None,
                message_ids=None,
            ):
                calls.update(
                    {
                        "chat": chat,
                        "limit": limit,
                        "since_iso": since_iso,
                        "until_iso": until_iso,
                        "offset_id": offset_id,
                        "message_ids": message_ids,
                    }
                )
                return []

        original_bridge = server_module.bridge
        server_module.bridge = _BridgeStub()
        try:
            result = await server_module.tg_read_messages(
                chat="-1001234567890",
                limit=50,
                since="2026-01-15T16:30:00+00:00",
                until="2026-01-15T17:30:00+00:00",
                offset_id=12880,
                message_id=12878,
                message_ids=[12879],
            )
        finally:
            server_module.bridge = original_bridge

        self.assertEqual(result["status"], "ok")
        self.assertEqual(calls, {
            "chat": "-1001234567890",
            "limit": 50,
            "since_iso": "2026-01-15T16:30:00+00:00",
            "until_iso": "2026-01-15T17:30:00+00:00",
            "offset_id": 12880,
            "message_ids": [12878, 12879],
        })


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
        file_download_roots=(),
    )


if __name__ == "__main__":
    unittest.main()
