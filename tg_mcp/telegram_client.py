from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import mimetypes
from pathlib import Path
from typing import Any, Iterable, cast

from telethon import TelegramClient
from telethon.tl.functions.channels import EditBannedRequest, InviteToChannelRequest
from telethon.tl.functions.messages import CreateChatRequest
from telethon.tl.functions.messages import AddChatUserRequest, DeleteChatUserRequest
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import ChatBannedRights
from telethon.utils import get_display_name, get_peer_id

from .config import Settings
from .session import read_session_string


@dataclass
class TgMessage:
    id: int
    chat_id: int
    sender_id: int | None
    date_iso: str
    text: str
    forwarded_from: dict[str, Any] | None
    reactions: list[dict[str, Any]]
    recent_reactions: list[dict[str, Any]]
    attachment_count: int
    attachments: list[dict[str, Any]]


@dataclass(frozen=True)
class TgFolder:
    id: int
    name: str
    peer_ids: frozenset[int] = field(default_factory=frozenset)


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
            if not await _is_user_authorized(client):
                await _disconnect_client(client)
                raise RuntimeError(
                    "Telegram session is not authorized. Run 'python -m tg_mcp.login' first "
                    "or copy a valid .tg_string_session.txt into TG_SESSION_PATH."
                )

            self._client = client
            return client

    async def disconnect(self) -> None:
        async with self._lock:
            if self._client is not None:
                await _disconnect_client(self._client)
                self._client = None

    async def send_message(
        self,
        chat: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        client = await self.ensure_connected()
        entity = cast(Any, await self._resolve_entity(client, chat))
        client_any = cast(Any, client)
        send_kwargs: dict[str, Any] = {}
        if reply_to_message_id is not None:
            send_kwargs["reply_to"] = reply_to_message_id
        message = await client_any.send_message(entity, text, **send_kwargs)
        return {
            "chat": chat,
            "message_id": message.id,
            "date": _to_iso(message.date),
        }

    async def create_group(self, title: str) -> dict[str, Any]:
        normalized_title = _normalize_group_title(title)

        client = await self.ensure_connected()
        client_any = cast(Any, client)
        result = await client_any(CreateChatRequest(users=[], title=normalized_title))
        chat = _extract_created_chat(result)

        return {
            "chat_id": _get_chat_id(chat),
            "title": _extract_chat_title(chat) or normalized_title,
        }

    async def add_group_member(self, chat: str, member: str) -> dict[str, Any]:
        normalized_member = _normalize_member(member)

        client = await self.ensure_connected()
        group = cast(Any, await self._resolve_entity(client, chat))
        member_entity = await self._resolve_member_input(client, normalized_member)
        client_any = cast(Any, client)

        if _is_basic_group(group):
            await client_any(AddChatUserRequest(chat_id=_get_group_id(group), user_id=member_entity, fwd_limit=0))
        elif _is_channel_group(group):
            await client_any(InviteToChannelRequest(channel=group, users=[member_entity]))
        else:
            raise ValueError(f"unsupported_chat_type: '{type(group).__name__}'")

        return {
            "chat": chat,
            "member": normalized_member,
            "action": "add",
        }

    async def remove_group_member(self, chat: str, member: str) -> dict[str, Any]:
        normalized_member = _normalize_member(member)

        client = await self.ensure_connected()
        group = cast(Any, await self._resolve_entity(client, chat))
        member_entity = await self._resolve_member_input(client, normalized_member)
        client_any = cast(Any, client)

        if _is_basic_group(group):
            await client_any(DeleteChatUserRequest(chat_id=_get_group_id(group), user_id=member_entity, revoke_history=False))
        elif _is_channel_group(group):
            banned_rights = ChatBannedRights(until_date=None, view_messages=True)
            await client_any(EditBannedRequest(channel=group, participant=member_entity, banned_rights=banned_rights))
            unbanned_rights = ChatBannedRights(until_date=None, view_messages=False)
            await client_any(EditBannedRequest(channel=group, participant=member_entity, banned_rights=unbanned_rights))
        else:
            raise ValueError(f"unsupported_chat_type: '{type(group).__name__}'")

        return {
            "chat": chat,
            "member": normalized_member,
            "action": "remove",
        }

    async def send_file(self, chat: str, file_path: str | Path | Iterable[str | Path], caption: str | None = None) -> dict[str, Any]:
        paths = _normalize_file_paths(file_path)
        for path in paths:
            if not path.exists():
                raise ValueError(f"file_not_found: '{path}'")
            if not path.is_file():
                raise ValueError(f"not_a_file: '{path}'")

        client = await self.ensure_connected()
        entity = cast(Any, await self._resolve_entity(client, chat))
        client_any = cast(Any, client)
        files_arg: Any = paths[0] if len(paths) == 1 else paths
        sent = await client_any.send_file(entity, file=files_arg, caption=caption)
        messages = sent if isinstance(sent, list) else [sent]
        attachments = [_build_attachment_payload(path, message) for path, message in zip(paths, messages, strict=True)]
        result = {
            "chat": chat,
            "caption": caption,
            "attachment_count": len(attachments),
            "attachments": attachments,
        }
        if attachments:
            result.update(attachments[0])
        return result

    async def download_attachment(self, chat: str, message_id: int, output_dir: str | Path) -> dict[str, Any]:
        target_dir = Path(output_dir).expanduser()

        client = await self.ensure_connected()
        entity = cast(Any, await self._resolve_entity(client, chat))
        client_any = cast(Any, client)
        message = await client_any.get_messages(entity, ids=message_id)

        if message is None:
            raise ValueError(f"message_not_found: '{message_id}'")
        if getattr(message, "media", None) is None:
            raise ValueError(f"message_has_no_attachment: '{message_id}'")

        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded = await client_any.download_media(message, file=str(target_dir))
        if not downloaded:
            raise RuntimeError(f"attachment_download_failed: '{message_id}'")

        downloaded_path = Path(downloaded).expanduser().resolve()
        if not downloaded_path.exists() or not downloaded_path.is_file():
            raise RuntimeError(f"attachment_download_failed: '{message_id}'")

        return {
            "chat": chat,
            "message_id": int(message.id),
            "date": _to_iso(getattr(message, "date", None)),
            "saved_path": str(downloaded_path),
            "file_name": downloaded_path.name,
            "file_size": downloaded_path.stat().st_size,
            "attachment_type": _detect_attachment_type(downloaded_path),
        }

    async def read_messages(
        self,
        chat: str,
        limit: int = 20,
        since_iso: str | None = None,
        until_iso: str | None = None,
        offset_id: int | None = None,
        message_ids: Iterable[int] | None = None,
    ) -> list[TgMessage]:
        client = await self.ensure_connected()
        entity = cast(Any, await self._resolve_entity(client, chat))
        client_any = cast(Any, client)

        normalized_ids = _normalize_message_ids(message_ids)
        if normalized_ids:
            raw_messages = await client_any.get_messages(
                entity,
                ids=normalized_ids[0] if len(normalized_ids) == 1 else normalized_ids,
            )
            messages = raw_messages if isinstance(raw_messages, list) else [raw_messages]
            result = [_build_tg_message(m) for m in messages if m is not None]
            result.sort(key=lambda x: x.id)
            return result

        limit = _normalize_message_limit(limit)

        since_dt = _parse_since(since_iso)
        until_dt = _parse_since(until_iso)
        result: list[TgMessage] = []

        iter_kwargs: dict[str, Any] = {"limit": limit}
        if until_dt is not None:
            iter_kwargs["offset_date"] = until_dt
        if offset_id is not None:
            iter_kwargs["offset_id"] = max(0, int(offset_id))

        async for m in client_any.iter_messages(entity, **iter_kwargs):
            if since_dt is not None and m.date is not None:
                msg_dt = _to_utc(m.date)
                if msg_dt < since_dt:
                    if until_dt is not None or offset_id is not None:
                        break
                    continue

            result.append(_build_tg_message(m))

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
            if not _dialog_in_folder(dialog, selected):
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

        for item in _iter_dialog_filters(raw_filters):
            folder_id = getattr(item, "id", None)
            if not isinstance(folder_id, int) or folder_id in seen_ids:
                continue

            name = _extract_folder_name(item)
            if not name:
                continue

            seen_ids.add(folder_id)
            folders.append(TgFolder(id=folder_id, name=name, peer_ids=_extract_filter_peer_ids(item)))

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

    async def _resolve_member_input(self, client: TelegramClient, member: str):
        try:
            return await client.get_input_entity(_parse_int(member) if _parse_int(member) is not None else member)
        except Exception as exc:
            raise ValueError(f"member_not_found: '{member}'") from exc


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


def _normalize_message_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > 100:
        return 100
    return limit


def _normalize_message_ids(message_ids: Iterable[int] | None) -> list[int]:
    if message_ids is None:
        return []

    result: list[int] = []
    seen: set[int] = set()
    for raw_id in message_ids:
        message_id = int(raw_id)
        if message_id < 1:
            raise ValueError("message_id must be positive")
        if message_id in seen:
            continue
        seen.add(message_id)
        result.append(message_id)
    return result


def _build_tg_message(message: Any) -> TgMessage:
    attachments = _extract_message_attachments(message)
    return TgMessage(
        id=int(getattr(message, "id", 0) or 0),
        chat_id=getattr(message, "chat_id", 0) or 0,
        sender_id=getattr(message, "sender_id", None),
        date_iso=_to_iso(getattr(message, "date", None)),
        text=(getattr(message, "message", None) or ""),
        forwarded_from=_serialize_forwarded_from(message),
        reactions=_serialize_reaction_counts(getattr(message, "reactions", None)),
        recent_reactions=_serialize_recent_reactions(getattr(message, "reactions", None)),
        attachment_count=len(attachments),
        attachments=attachments,
    )


def _serialize_forwarded_from(message: Any) -> dict[str, Any] | None:
    header = getattr(message, "fwd_from", None)
    if header is None:
        return None

    forward = getattr(message, "forward", None)
    sender_id = getattr(forward, "sender_id", None)
    if not isinstance(sender_id, int):
        source_peer = (
            getattr(header, "from_id", None)
            or getattr(header, "saved_from_id", None)
            or getattr(header, "saved_from_peer", None)
        )
        sender_id = _get_chat_id(source_peer) or None

    sender_name = ""
    sender = getattr(forward, "sender", None)
    if sender is not None:
        sender_name = get_display_name(sender).strip()
    if not sender_name:
        for attr_name in ("from_name", "saved_from_name"):
            raw_name = getattr(header, attr_name, None)
            if isinstance(raw_name, str) and raw_name.strip():
                sender_name = raw_name.strip()
                break

    result: dict[str, Any] = {
        "sender_id": sender_id,
        "sender_name": sender_name or None,
        "date_iso": _to_iso(getattr(header, "date", None)),
    }

    source_message_id = getattr(header, "channel_post", None)
    if not isinstance(source_message_id, int):
        source_message_id = getattr(header, "saved_from_msg_id", None)
    if isinstance(source_message_id, int):
        result["source_message_id"] = source_message_id

    post_author = getattr(header, "post_author", None)
    if isinstance(post_author, str) and post_author.strip():
        result["post_author"] = post_author.strip()

    return result


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _normalize_group_title(title: str) -> str:
    normalized = (title or "").strip()
    if not normalized:
        raise ValueError("invalid_title: title must be non-empty")
    return normalized


def _normalize_member(member: str) -> str:
    normalized = (member or "").strip()
    if not normalized:
        raise ValueError("member is required")
    return normalized


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


def _iter_dialog_filters(raw_filters: Any) -> Iterable[Any]:
    if raw_filters is None:
        return ()

    filters = getattr(raw_filters, "filters", None)
    if filters is not None:
        if isinstance(filters, Iterable):
            return filters
        return ()

    if isinstance(raw_filters, Iterable):
        return raw_filters

    return ()


def _extract_filter_peer_ids(dialog_filter: Any) -> frozenset[int]:
    peer_ids: set[int] = set()
    for attr_name in ("pinned_peers", "include_peers"):
        peers = getattr(dialog_filter, attr_name, None)
        if not isinstance(peers, Iterable):
            continue
        for peer in peers:
            try:
                peer_ids.add(int(get_peer_id(peer)))
            except Exception:
                continue
    return frozenset(peer_ids)


def _dialog_in_folder(dialog: Any, folder: TgFolder) -> bool:
    dialog_folder_id = getattr(dialog, "folder_id", None)
    if dialog_folder_id == folder.id:
        return True

    if not folder.peer_ids:
        return False

    entity = getattr(dialog, "entity", None)
    try:
        dialog_peer_id = int(get_peer_id(entity))
    except Exception:
        return False

    return dialog_peer_id in folder.peer_ids


def _serialize_reaction_counts(reactions: Any) -> list[dict[str, Any]]:
    raw_results = getattr(reactions, "results", None)
    if not isinstance(raw_results, Iterable):
        return []

    serialized: list[dict[str, Any]] = []
    for item in raw_results:
        reaction = _extract_reaction_value(getattr(item, "reaction", None))
        if not reaction:
            continue
        serialized.append(
            {
                "reaction": reaction,
                "count": int(getattr(item, "count", 0) or 0),
                "chosen_order": getattr(item, "chosen_order", None),
            }
        )
    return serialized


def _serialize_recent_reactions(reactions: Any) -> list[dict[str, Any]]:
    raw_recent = getattr(reactions, "recent_reactions", None)
    if not isinstance(raw_recent, Iterable):
        return []

    serialized: list[dict[str, Any]] = []
    for item in raw_recent:
        peer = getattr(item, "peer_id", None)
        serialized.append(
            {
                "peer_id": _get_chat_id(peer),
                "date_iso": _to_iso(getattr(item, "date", None)),
                "reaction": _extract_reaction_value(getattr(item, "reaction", None)),
                "big": bool(getattr(item, "big", False)),
                "unread": bool(getattr(item, "unread", False)),
                "my": bool(getattr(item, "my", False)),
            }
        )
    return serialized


def _extract_reaction_value(reaction: Any) -> str:
    emoticon = getattr(reaction, "emoticon", None)
    if isinstance(emoticon, str) and emoticon:
        return emoticon

    document_id = getattr(reaction, "document_id", None)
    if isinstance(document_id, int):
        return str(document_id)

    rendered = str(reaction).strip() if reaction is not None else ""
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


def _extract_chat_title(entity: Any) -> str:
    title = getattr(entity, "title", None)
    if isinstance(title, str):
        return title.strip()
    return ""


def _is_basic_group(entity: Any) -> bool:
    return type(entity).__name__ == "Chat"


def _is_channel_group(entity: Any) -> bool:
    return type(entity).__name__ == "Channel" and bool(getattr(entity, "megagroup", False))


def _get_group_id(entity: Any) -> int:
    raw_id = getattr(entity, "id", None)
    if isinstance(raw_id, int):
        return raw_id
    raise ValueError(f"unsupported_chat_type: '{type(entity).__name__}'")


def _extract_created_chat(result: Any) -> Any:
    chats = getattr(result, "chats", None)
    if isinstance(chats, list) and chats:
        return chats[0]

    updates = getattr(result, "updates", None)
    update_chats = getattr(updates, "chats", None)
    if isinstance(update_chats, list) and update_chats:
        return update_chats[0]

    raise RuntimeError("create_group_failed: Telegram API did not return created chat")


def _normalize_file_paths(file_path: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(file_path, (str, Path)):
        values = [file_path]
    else:
        values = list(file_path)

    if not values:
        raise ValueError("file_path is required")

    return [Path(value).expanduser() for value in values]


def _build_attachment_payload(path: Path, message: Any) -> dict[str, Any]:
    return {
        "message_id": message.id,
        "date": _to_iso(message.date),
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "attachment_type": _detect_attachment_type(path),
    }


def _extract_message_attachments(message: Any) -> list[dict[str, Any]]:
    if getattr(message, "media", None) is None:
        return []

    file_obj = getattr(message, "file", None)
    attachment = {
        "message_id": int(getattr(message, "id", 0) or 0),
        "date": _to_iso(getattr(message, "date", None)),
        "attachment_type": _detect_message_attachment_type(message, file_obj),
    }

    file_name = _extract_message_file_name(file_obj)
    if file_name:
        attachment["file_name"] = file_name

    file_size = _extract_message_file_size(file_obj)
    if file_size is not None:
        attachment["file_size"] = file_size

    mime_type = _extract_message_mime_type(file_obj)
    if mime_type:
        attachment["mime_type"] = mime_type

    return [attachment]


def _extract_message_file_name(file_obj: Any) -> str | None:
    name = getattr(file_obj, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _extract_message_file_size(file_obj: Any) -> int | None:
    raw_size = getattr(file_obj, "size", None)
    if isinstance(raw_size, int):
        return raw_size
    return None


def _extract_message_mime_type(file_obj: Any) -> str | None:
    mime_type = getattr(file_obj, "mime_type", None)
    if isinstance(mime_type, str) and mime_type.strip():
        return mime_type.strip()
    return None


def _detect_message_attachment_type(message: Any, file_obj: Any) -> str:
    mime_type = _extract_message_mime_type(file_obj)
    if mime_type:
        major_type = mime_type.split("/", 1)[0]
        if major_type == "image":
            return "photo"
        if major_type == "video":
            return "video"
        if major_type == "audio":
            return "audio"

    if getattr(message, "photo", None) is not None:
        return "photo"
    if getattr(message, "video", None) is not None:
        return "video"
    if getattr(message, "audio", None) is not None or getattr(message, "voice", None) is not None:
        return "audio"

    return "document"


def _detect_attachment_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type is None:
        return "document"
    major_type = mime_type.split("/", 1)[0]
    if major_type == "image":
        return "photo"
    if major_type == "video":
        return "video"
    if major_type == "audio":
        return "audio"
    return "document"


async def _disconnect_client(client: TelegramClient) -> None:
    result = client.disconnect()
    if asyncio.iscoroutine(result):
        await result


async def _is_user_authorized(client: TelegramClient) -> bool:
    result = client.is_user_authorized()
    if asyncio.iscoroutine(result):
        return bool(await result)
    return bool(result)
