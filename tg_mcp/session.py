from __future__ import annotations

from pathlib import Path


def read_session_string(session_path: Path) -> str | None:
    if not session_path.exists():
        return None
    value = session_path.read_text(encoding="utf-8").strip()
    return value or None


def write_session_string(session_path: Path, value: str) -> None:
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(value.strip(), encoding="utf-8")
