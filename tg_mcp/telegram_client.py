from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.utils import get_peer_id

from .config import Settings
from .session import read_session_string


@dataclass
class TgMessage:
    id: int
    chat_id: int
    sender_id: int | None
    date_iso: str
    text: str


@dataclass(frozen=True)
class TgFolder:
    id: int
    name: str


@dataclass
class TgFolderChat:
    chat_id: int
    title: str
    username: str | None
    is_channel: bool
    unread_count: int
    folder_id: int
    pinned: bool
    last_message_date: str
    entity_type: str


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
        entity = await self._resolve_entity(client, chat)
        message = await client.send_message(entity, text)
        return {
            "chat": chat,
            "message_id": message.id,
            "date": _to_iso(message.date),
        }

    async def read_messages(self, chat: str, limit: int = 20, since_iso: str | None = None) -> list[TgMessage]:
        client = await self.ensure_connected()
        entity = await self._resolve_entity(client, chat)

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

    async def list_folder_chats(self, folder: str, limit: int = 200) -> dict[str, Any]:
        query = (folder or "").strip()
        if not query:
            raise ValueError("invalid_folder: folder must be non-empty")
        if limit < 1 or limit > 500:
            raise ValueError("invalid_limit: limit must be between 1 and 500")

        client = await self.ensure_connected()
        folders = await self._load_folders(client)
        selected = _select_folder(folders, query)

        chats: list[TgFolderChat] = []
        async for dialog in client.iter_dialogs():
            if getattr(dialog, "folder_id", None) != selected.id:
                continue

            entity = getattr(dialog, "entity", None)
            username_raw = getattr(entity, "username", None)
            username = username_raw.strip() if isinstance(username_raw, str) and username_raw.strip() else None
            last_message_date = ""

            message = getattr(dialog, "message", None)
            if message is not None:
                last_message_date = _to_iso(getattr(message, "date", None))

            chats.append(
                TgFolderChat(
                    chat_id=_get_chat_id(entity),
                    title=(getattr(dialog, "name", "") or "").strip(),
                    username=username,
                    is_channel=bool(getattr(dialog, "is_channel", False)),
                    unread_count=int(getattr(dialog, "unread_count", 0) or 0),
                    folder_id=selected.id,
                    pinned=bool(getattr(dialog, "pinned", False)),
                    last_message_date=last_message_date,
                    entity_type=type(entity).__name__ if entity is not None else "Unknown",
                )
            )

            if len(chats) >= limit:
                break

        return {
            "folder": selected.name,
            "folder_id": selected.id,
            "count": len(chats),
            "chats": [c.__dict__ for c in chats],
        }

    async def _load_folders(self, client: TelegramClient) -> list[TgFolder]:
        raw_filters = await client(GetDialogFiltersRequest())
        folders: list[TgFolder] = []
        seen_ids: set[int] = set()

        for item in raw_filters:
            folder_id = getattr(item, "id", None)
            if not isinstance(folder_id, int) or folder_id in seen_ids:
                continue

            name = _extract_folder_name(item)
            if not name:
                continue

            seen_ids.add(folder_id)
            folders.append(TgFolder(id=folder_id, name=name))

        return folders

    async def _resolve_entity(self, client: TelegramClient, chat: str):
        value = (chat or "").strip()
        try:
            return await client.get_entity(value)
        except Exception:
            pass

        wanted = value.casefold()
        numeric = _parse_int(value)

        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            name = (dialog.name or "").strip()
            if name and name.casefold() == wanted:
                return entity

            if numeric is not None:
                ent_id = getattr(entity, "id", None)
                if isinstance(ent_id, int) and ent_id == numeric:
                    return entity

                try:
                    peer_id = get_peer_id(entity)
                except Exception:
                    peer_id = None
                if isinstance(peer_id, int) and peer_id == numeric:
                    return entity

        raise ValueError(f"Cannot find any entity corresponding to '{chat}'")


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


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _extract_folder_name(dialog_filter: Any) -> str:
    title = getattr(dialog_filter, "title", None)
    if isinstance(title, str):
        return title.strip()

    text = getattr(title, "text", None)
    if isinstance(text, str):
        return text.strip()

    if title is None:
        return ""

    rendered = str(title).strip()
    if not rendered or rendered == "None":
        return ""
    return rendered


def _select_folder(folders: list[TgFolder], query: str) -> TgFolder:
    wanted = query.casefold()
    partial = [folder for folder in folders if wanted in folder.name.casefold()]

    if not partial:
        available = ", ".join(sorted(folder.name for folder in folders)) or "none"
        raise ValueError(f"folder_not_found: '{query}'. Available folders: {available}")

    if len(partial) == 1:
        return partial[0]

    exact = [folder for folder in partial if folder.name.casefold() == wanted]
    if len(exact) == 1:
        return exact[0]

    candidates = ", ".join(sorted({folder.name for folder in partial}))
    raise ValueError(f"folder_ambiguous: '{query}'. Candidates: {candidates}")


def _get_chat_id(entity: Any) -> int:
    try:
        return int(get_peer_id(entity))
    except Exception:
        pass

    raw_id = getattr(entity, "id", None)
    if isinstance(raw_id, int):
        return raw_id
    return 0
