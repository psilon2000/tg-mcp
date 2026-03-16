# tg-mcp

MCP server (Python + Telethon) for Telegram chat automation.

It supports:
- sending commands/messages to a target chat,
- sending file attachments,
- reading recent messages,
- listing chats from a Telegram folder,
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
- `TG_WRITE_CHAT_WHITELIST` (comma-separated chats allowed for writes; for example `me,@my_bot,123456789`)
- optional `TG_FILE_SEND_ROOTS` (comma-separated directories allowed for file uploads; when unset, only absolute file paths are accepted)

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

- `tg_send_message(text, chat=None, confirm=False)`
- `tg_send_file(file_path=None, file_paths=None, caption=None, chat=None, confirm=False)`
- `tg_read_messages(chat=None, limit=20, since=None)`
- `tg_list_folder_chats(folder, limit=200)`
- `tg_wait_reply(after_id, timeout_sec=30, chat=None)`
- `tg_auth_status()`

If `chat` is omitted, server uses `TG_DEFAULT_CHAT`.

Write safety rules for `tg_send_message` and `tg_send_file`:
- `confirm` must be explicitly set to `true`.
- target chat must be present in `TG_WRITE_CHAT_WHITELIST`.

`tg_send_file` behavior:
- accepts either one `file_path` or multiple `file_paths`.
- every path must point to an existing regular file.
- if `TG_FILE_SEND_ROOTS` is set, resolved file path must stay inside one of those directories.
- if `TG_FILE_SEND_ROOTS` is not set, `file_path` must be absolute.
- `caption` is optional and sent as the Telegram attachment caption.
- response includes `caption`, `attachment_count`, and per-file metadata in `attachments` with `attachment_type`.

Example:

```json
{
  "file_paths": [
    "/mnt/d/repository/tg-mcp/README.md",
    "/mnt/d/repository/tg-mcp/.env.example"
  ],
  "caption": "Current MCP docs",
  "chat": "me",
  "confirm": true
}
```

`tg_list_folder_chats` behavior:
- `folder` supports case-insensitive partial matching.
- if partial match returns multiple folders, tool tries exact match (case-insensitive).
- if exact disambiguation still fails, tool returns `folder_ambiguous` with candidates.
- if folder exists but has no chats, tool returns `status=ok`, `count=0`, `chats=[]`.
- `limit` must be in range `1..500`.

Example:

```json
{
  "folder": "Module",
  "folder_id": 3,
  "count": 2,
  "chats": [
    {
      "chat_id": -100123,
      "title": "ЦР Внедрение",
      "username": null,
      "is_channel": true,
      "unread_count": 0,
      "folder_id": 3,
      "pinned": false,
      "last_message_date": "2026-03-06T09:00:00+00:00",
      "entity_type": "Channel"
    }
  ]
}
```

## Example Flow

1. Call `tg_send_message` with `/run_now 2026-03-02`.
2. Take returned `message_id`.
3. Call `tg_wait_reply(after_id=<message_id>)`.
4. Call `tg_read_messages(limit=20)` for context.
