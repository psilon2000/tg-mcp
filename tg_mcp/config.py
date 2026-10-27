from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    session_path: Path
    default_chat: str | None
    twofa_password: str | None
    write_chat_whitelist: tuple[str, ...]
    admin_chat_whitelist: tuple[str, ...]
    file_send_roots: tuple[Path, ...]
    file_download_roots: tuple[Path, ...] = ()


def load_settings() -> Settings:
    load_dotenv()

    api_id_raw = os.getenv("TG_API_ID", "0").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    session_path = Path(os.getenv("TG_SESSION_PATH", ".tg_string_session.txt").strip())
    default_chat = os.getenv("TG_DEFAULT_CHAT", "").strip() or None
    twofa_password = os.getenv("TG_2FA_PASSWORD", "").strip() or None
    write_chat_whitelist = tuple(
        item.strip() for item in os.getenv("TG_WRITE_CHAT_WHITELIST", "").split(",") if item.strip()
    )
    admin_chat_whitelist = tuple(
        item.strip() for item in os.getenv("TG_ADMIN_CHAT_WHITELIST", "").split(",") if item.strip()
    )
    file_send_roots = tuple(
        Path(item.strip()).expanduser().resolve()
        for item in os.getenv("TG_FILE_SEND_ROOTS", "").split(",")
        if item.strip()
    )
    file_download_roots = tuple(
        Path(item.strip()).expanduser().resolve()
        for item in os.getenv("TG_FILE_DOWNLOAD_ROOTS", "").split(",")
        if item.strip()
    )

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("TG_API_ID must be an integer") from exc

    if api_id <= 0:
        raise RuntimeError("TG_API_ID is required")
    if not api_hash:
        raise RuntimeError("TG_API_HASH is required")

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        session_path=session_path,
        default_chat=default_chat,
        twofa_password=twofa_password,
        write_chat_whitelist=write_chat_whitelist,
        admin_chat_whitelist=admin_chat_whitelist,
        file_send_roots=file_send_roots,
        file_download_roots=file_download_roots,
    )
