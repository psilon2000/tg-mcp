# tg-mcp

MCP server (Python + Telethon) for Telegram chat automation.

It supports:
- creating a regular private Telegram group,
- adding/removing members in admin-whitelisted Telegram groups,
- sending commands/messages to a target chat,
- sending file attachments,
- downloading file attachments from messages,
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
- `TG_ADMIN_CHAT_WHITELIST` (comma-separated groups allowed for member admin operations; for example `Ops,@team_group,-1001234567890`)
- optional `TG_FILE_SEND_ROOTS` (comma-separated directories allowed for file uploads; when unset, only absolute file paths are accepted)
- optional `TG_FILE_DOWNLOAD_ROOTS` (comma-separated directories allowed for downloaded attachments; when unset, only absolute output directories are accepted)

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

- `tg_create_group(title)`
- `tg_add_group_member(chat, member, confirm=False)`
- `tg_remove_group_member(chat, member, confirm=False)`
- `tg_send_message(text, chat=None, reply_to_message_id=None, confirm=False)`
- `tg_send_file(file_path=None, file_paths=None, caption=None, chat=None, confirm=False)`
- `tg_download_attachment(message_id, output_dir, chat=None)`
- `tg_read_messages(chat=None, limit=20, since=None, until=None, offset_id=None, message_id=None, message_ids=None)`
- `tg_list_folder_chats(folder, limit=200)`
- `tg_wait_reply(after_id, timeout_sec=30, chat=None)`
- `tg_auth_status()`

If `chat` is omitted, server uses `TG_DEFAULT_CHAT`.

`tg_create_group` behavior:
- creates a regular private Telegram group from the authorized user account in `TG_SESSION_PATH`.
- accepts one required parameter: `title`.
- rejects empty or whitespace-only titles locally.
- returns `status`, `chat_id`, and `title`.
- does not require `confirm` or whitelist in the current MVP.

`tg_add_group_member` / `tg_remove_group_member` behavior:
- require explicit `chat`, `member`, and `confirm=true`.
- require target `chat` to be present in `TG_ADMIN_CHAT_WHITELIST`.
- `member` accepts `@username` or numeric id.
- support regular groups and megagroups; unsupported chat types return `unsupported_chat_type`.
- return `status`, `chat`, `member`, and `action`.

Example add:

```json
{
  "chat": "Ops",
  "member": "@alice",
  "confirm": true
}
```

Example remove:

```json
{
  "chat": "Ops",
  "member": "123456789",
  "confirm": true
}
```

Example:

```json
{
  "title": "Launch Squad"
}
```

Write safety rules for `tg_send_message` and `tg_send_file`:
- `confirm` must be explicitly set to `true`.
- target chat must be present in `TG_WRITE_CHAT_WHITELIST`.

`tg_send_message` behavior:
- `reply_to_message_id` is optional.
- when set, the message is sent as a reply to that Telegram message id.

Example:

```json
{
  "text": "Got it, thanks",
  "chat": "Ops",
  "reply_to_message_id": 1020,
  "confirm": true
}
```

Admin safety rules for `tg_add_group_member` and `tg_remove_group_member`:
- `confirm` must be explicitly set to `true`.
- target chat must be present in `TG_ADMIN_CHAT_WHITELIST`.

`tg_send_file` behavior:
- accepts either one `file_path` or multiple `file_paths`.
- every path must point to an existing regular file.
- if `TG_FILE_SEND_ROOTS` is set, resolved file path must stay inside one of those directories.
- if `TG_FILE_SEND_ROOTS` is not set, `file_path` must be absolute.
- `caption` is optional and sent as the Telegram attachment caption.
- response includes `caption`, `attachment_count`, and per-file metadata in `attachments` with `attachment_type`.

Send rate limits (`tg_send_message`, `tg_send_file`):
- sends use the user's personal account; on 27.10.2026 a batch to Saved Messages hit FloodWait twice: after 21 messages in 86 s (wait 212 s) and after 23 messages in 108 s (wait 184 s).
- an album of N files in `tg_send_file` counts as N messages.
- for batches send at most ~6 messages in a row and pause ~45 s; merge many documents into a few PDF bundles with a table of contents instead of dozens of separate files.
- `reply_to_message_id` lets you attach copy-ready text to an explanatory message, so the user copies only the text.
- the same rules are exposed to every MCP client via the server `instructions` and the send tool descriptions.

`tg_download_attachment` behavior:
- requires `message_id` and `output_dir`.
- downloads the attachment from the target message into `output_dir`.
- if `TG_FILE_DOWNLOAD_ROOTS` is set, resolved output directory must stay inside one of those directories.
- if `TG_FILE_DOWNLOAD_ROOTS` is not set, `output_dir` must be absolute.
- returns saved path and attachment metadata.

`tg_read_messages` behavior:
- returns messages in ascending id order.
- `message_id` or `message_ids` returns exact Telegram messages by id.
- `until` is an upper date bound; combine it with `since` to read an old time window instead of only recent messages.
- `offset_id` reads older messages before the given Telegram message id.
- includes `reactions` and `recent_reactions` when present.
- includes `forwarded_from` with the original sender id, display name, and message date for forwarded messages; the field is `null` for regular messages.
- includes `attachment_count` and `attachments` for messages with Telegram media.
- each attachment entry may include `file_name`, `file_size`, `mime_type`, and `attachment_type` when Telegram exposes them.

Example old window:

```json
{
  "chat": "-1001234567890",
  "since": "2026-01-15T17:00:00+00:00",
  "until": "2026-01-15T17:30:00+00:00",
  "limit": 100
}
```

Example exact messages:

```json
{
  "chat": "-1001234567890",
  "message_ids": [1201, 1202]
}
```

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

Example download:

```json
{
  "chat": "example_user",
  "message_id": 4321,
  "output_dir": "/tmp/tg-downloads"
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

## Real Telegram E2E

- `tests/test_create_group_e2e.py` uses a live Telegram session and is skipped by default.
- Run it only manually with `TG_RUN_REAL_E2E=1`.
- The test creates a group named `tg-mcp-e2e-<timestamp>`.
- Cleanup is manual for now: archive or delete the test group from Telegram after the run.
- `tests/test_group_member_admin_e2e.py` also uses a live Telegram session and is skipped by default.
- For member admin live tests, set `TG_REAL_ADMIN_TEST_CHAT` and `TG_REAL_ADMIN_TEST_MEMBER` to a dedicated non-production group and test account.
- Cleanup for member admin live tests is manual: return the test member/group to the expected state after the run.
