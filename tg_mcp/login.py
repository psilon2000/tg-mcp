from __future__ import annotations

import asyncio
import os
from getpass import getpass

from telethon import TelegramClient
from telethon.errors import PasswordHashInvalidError, SessionPasswordNeededError
from telethon.sessions import StringSession

from .config import load_settings
from .session import write_session_string


async def _run_login() -> None:
    settings = load_settings()

    client = TelegramClient(
        StringSession(),
        settings.api_id,
        settings.api_hash,
        device_model="tg-mcp-login",
        app_version="0.1.0",
        system_version="linux",
        lang_code="en",
    )

    await client.connect()
    phone = os.getenv("TG_PHONE", "").strip() or input("Phone (+...): ").strip()

    try:
        await client.send_code_request(phone)
        code = input("Code from Telegram: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = settings.twofa_password or getpass("2FA password: ").strip()
            try:
                await client.sign_in(password=password)
            except PasswordHashInvalidError as exc:
                raise RuntimeError("Invalid 2FA password") from exc

        session_value = client.session.save()
        write_session_string(settings.session_path, session_value)
        print(f"Session saved to {settings.session_path}")
    finally:
        await client.disconnect()


def main() -> None:
    asyncio.run(_run_login())


if __name__ == "__main__":
    main()
