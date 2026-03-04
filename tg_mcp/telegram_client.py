from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import Settings
from .session import read_session_string


@dataclass
class TgMessage:
    id: int
    chat_id: int
    sender_id: int | None
    date_iso: str
    text: str


class TelegramBridge:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: TelegramClient | None = None
        self._lock = asyncio.Lock()

    async def ensure_connected(self) -> TelegramClient:
        async with self._lock:
            if self._client is not None and self._client.is_connected():
                return self._client

            session = read_session_string(self._settings.session_path) or ""
            client = TelegramClient(
                StringSession(session),
                self._settings.api_id,
                self._settings.api_hash,
                device_model="tg-mcp",
                app_version="0.1.0",
                system_version="linux",
                lang_code="en",
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise RuntimeError(
                    "Telegram session is not authorized. Run 'python -m tg_mcp.login' first "
                    "or copy a valid .tg_string_session.txt into TG_SESSION_PATH."
                )

            self._client = client
            return client

    async def disconnect(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.disconnect()
                self._client = None

    async def send_message(self, chat: str, text: str) -> dict[str, Any]:
        client = await self.ensure_connected()
        entity = await client.get_entity(chat)
        message = await client.send_message(entity, text)
        return {
            "chat": chat,
            "message_id": message.id,
            "date": _to_iso(message.date),
        }

    async def read_messages(self, chat: str, limit: int = 20, since_iso: str | None = None) -> list[TgMessage]:
        client = await self.ensure_connected()
        entity = await client.get_entity(chat)

        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100

        since_dt = _parse_since(since_iso)
        result: list[TgMessage] = []

        async for m in client.iter_messages(entity, limit=limit):
            if since_dt is not None and m.date is not None:
                msg_dt = _to_utc(m.date)
                if msg_dt < since_dt:
                    continue

            result.append(
                TgMessage(
                    id=m.id,
                    chat_id=getattr(m, "chat_id", 0) or 0,
                    sender_id=getattr(m, "sender_id", None),
                    date_iso=_to_iso(m.date),
                    text=(m.message or ""),
                )
            )

        result.sort(key=lambda x: x.id)
        return result

    async def wait_reply(self, chat: str, after_id: int, timeout_sec: int = 30) -> dict[str, Any]:
        deadline = asyncio.get_event_loop().time() + max(1, min(timeout_sec, 180))
        while asyncio.get_event_loop().time() < deadline:
            messages = await self.read_messages(chat, limit=30)
            for msg in messages:
                if msg.id > after_id:
                    return {
                        "status": "ok",
                        "message": msg.__dict__,
                    }
            await asyncio.sleep(1)

        return {
            "status": "timeout",
            "after_id": after_id,
        }


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return _to_utc(dt).isoformat(timespec="seconds")


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _to_utc(parsed)
