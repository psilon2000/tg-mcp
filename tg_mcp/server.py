from __future__ import annotations

import atexit
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .telegram_client import TelegramBridge


settings = load_settings()
bridge = TelegramBridge(settings)
mcp = FastMCP("tg-mcp")


def _resolve_chat(chat: str | None) -> str:
    value = (chat or "").strip()
    if value:
        return value
    if settings.default_chat:
        return settings.default_chat
    raise ValueError("chat is required when TG_DEFAULT_CHAT is not set")


def _ensure_write_allowed(chat: str, confirm: bool) -> None:
    if not confirm:
        raise ValueError("write requires explicit confirm=true")

    if not settings.write_chat_whitelist:
        raise ValueError("write whitelist is empty: set TG_WRITE_CHAT_WHITELIST")

    if chat not in settings.write_chat_whitelist:
        raise ValueError(
            f"chat '{chat}' is not in write whitelist"
        )


def _resolve_send_file_path(file_path: str) -> Path:
    raw_value = (file_path or "").strip()
    if not raw_value:
        raise ValueError("file_path is required")

    candidate = Path(raw_value).expanduser()
    if settings.file_send_roots:
        resolved = candidate.resolve()
        for root in settings.file_send_roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue

        allowed = ", ".join(str(root) for root in settings.file_send_roots)
        raise ValueError(
            f"file_path '{resolved}' is outside allowed roots: {allowed}"
        )

    if not candidate.is_absolute():
        raise ValueError(
            "file_path must be absolute when TG_FILE_SEND_ROOTS is not set"
        )

    return candidate.resolve()


def _resolve_send_file_paths(
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> list[Path]:
    values: list[str] = []
    if file_path is not None:
        values.append(file_path)
    if file_paths is not None:
        values.extend(file_paths)

    if not values:
        raise ValueError("file_path or file_paths is required")

    resolved: list[Path] = []
    for value in values:
        resolved.append(_resolve_send_file_path(value))
    return resolved


@mcp.tool()
async def tg_send_message(text: str, chat: str | None = None, confirm: bool = False) -> dict[str, Any]:
    """Send message to Telegram chat/channel (whitelist + confirm required)."""
    target = _resolve_chat(chat)
    _ensure_write_allowed(target, confirm)
    result = await bridge.send_message(target, text)
    return {"status": "ok", **result}


@mcp.tool()
async def tg_create_group(title: str) -> dict[str, Any]:
    """Create a regular private Telegram group."""
    result = await bridge.create_group(title)
    return {"status": "ok", **result}


@mcp.tool()
async def tg_send_file(
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    caption: str | None = None,
    chat: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Send file attachment to Telegram chat/channel (whitelist + confirm required)."""
    target = _resolve_chat(chat)
    _ensure_write_allowed(target, confirm)
    resolved_paths = _resolve_send_file_paths(file_path=file_path, file_paths=file_paths)
    result = await bridge.send_file(target, resolved_paths, caption=caption)
    return {"status": "ok", **result}


@mcp.tool()
async def tg_read_messages(chat: str | None = None, limit: int = 20, since: str | None = None) -> dict[str, Any]:
    """Read latest messages from Telegram chat/channel."""
    target = _resolve_chat(chat)
    messages = await bridge.read_messages(target, limit=limit, since_iso=since)
    return {
        "status": "ok",
        "chat": target,
        "count": len(messages),
        "messages": [m.__dict__ for m in messages],
    }


@mcp.tool()
async def tg_list_folder_chats(folder: str, limit: int = 200) -> dict[str, Any]:
    """List chats from Telegram folder by name."""
    result = await bridge.list_folder_chats(folder=folder, limit=limit)
    return {
        "status": "ok",
        **result,
    }


@mcp.tool()
async def tg_wait_reply(after_id: int, timeout_sec: int = 30, chat: str | None = None) -> dict[str, Any]:
    """Wait for first message with id greater than after_id."""
    target = _resolve_chat(chat)
    result = await bridge.wait_reply(target, after_id=after_id, timeout_sec=timeout_sec)
    result["chat"] = target
    return result


@mcp.tool()
async def tg_auth_status() -> dict[str, Any]:
    """Check whether saved Telegram session is authorized."""
    try:
        await bridge.ensure_connected()
        return {
            "status": "ok",
            "authorized": True,
            "session_path": str(settings.session_path),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "status": "error",
            "authorized": False,
            "session_path": str(settings.session_path),
            "error": str(exc),
        }


def _shutdown() -> None:
    try:
        import asyncio

        asyncio.run(bridge.disconnect())
    except Exception:
        pass


atexit.register(_shutdown)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
