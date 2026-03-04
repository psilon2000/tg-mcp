# tg-mcp

MCP server (Python + Telethon) for Telegram chat automation.

It supports:
- sending commands/messages to a target chat,
- reading recent messages,
- waiting for a bot reply after a sent command,
- one-time login with saved StringSession.

## Setup

1. Create venv and install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure env:

```bash
cp .env.example .env
```

Set:
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_PATH` (default `.tg_string_session.txt`)
- optional `TG_DEFAULT_CHAT` (chat id or @username)

## Login Once

Run interactive login:

```bash
python -m tg_mcp.login
```

It saves StringSession to `TG_SESSION_PATH`.

You can also copy an existing compatible session file, for example:

```bash
cp /mnt/d/repository/module/scripts/tg/.tg_string_session.txt ./.tg_string_session.txt
```

## Run MCP Server

```bash
python -m tg_mcp.server
```

The server runs over stdio.

## Tools

- `tg_send_message(text, chat=None)`
- `tg_read_messages(chat=None, limit=20, since=None)`
- `tg_wait_reply(after_id, timeout_sec=30, chat=None)`
- `tg_auth_status()`

If `chat` is omitted, server uses `TG_DEFAULT_CHAT`.

## Example Flow

1. Call `tg_send_message` with `/run_now 2026-03-02`.
2. Take returned `message_id`.
3. Call `tg_wait_reply(after_id=<message_id>)`.
4. Call `tg_read_messages(limit=20)` for context.
