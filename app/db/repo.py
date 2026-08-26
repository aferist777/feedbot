"""Reads and writes that more than one module needs."""
import json
import sqlite3
import time
from typing import Any, Optional, Sequence

from app.db.base import q, q1, x


def now() -> int:
    return int(time.time())


# ----------------------------------------------------------------- settings


def sget(key: str, default: Optional[str] = None) -> Optional[str]:
    row = q1("SELECT value FROM settings WHERE key=?", key)
    return row["value"] if row else default


def sset(key: str, value: Any) -> None:
    x(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        key,
        "" if value is None else str(value),
    )


def sdel(key: str) -> None:
    x("DELETE FROM settings WHERE key=?", key)


def sget_int(key: str, default: Optional[int] = None) -> Optional[int]:
    raw = sget(key)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def sget_json(key: str, default: Any) -> Any:
    raw = sget(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def sset_json(key: str, value: Any) -> None:
    sset(key, json.dumps(value, ensure_ascii=False))


# -------------------------------------------------------------------- owner

# One row, so handing the bot to someone else does not touch any data.
# Telegram will not resolve a @username into an id for a bot the person has
# never written to, so a handover is a wait: the username is remembered and
# the binding happens on the first /start that matches it.


def owner_id() -> Optional[int]:
    return sget_int("owner_id")


def claim_owner(user_id: int, username: str = "") -> bool:
    """True when this /start made the caller the owner."""
    current = owner_id()
    if current is not None:
        return False
    expected = (sget("owner_username") or "").lstrip("@").lower()
    if expected and username.lstrip("@").lower() != expected:
        return False
    sset("owner_id", user_id)
    sdel("owner_username")
    return True


# -------------------------------------------------------------------- feeds


def feeds() -> Sequence[sqlite3.Row]:
    return q("SELECT * FROM feeds ORDER BY id")


def feed(feed_id: int) -> Optional[sqlite3.Row]:
    return q1("SELECT * FROM feeds WHERE id=?", feed_id)


def create_feed(name: str, note: str = "") -> int:
    return x(
        "INSERT INTO feeds(name, note, created_at) VALUES(?, ?, ?)",
        name.strip(), note.strip(), now(),
    )


def active_feed() -> Optional[sqlite3.Row]:
    """The feed the panel and the bot are currently pointed at.

    Falls back to the first one, so a fresh install and a deleted feed both
    land somewhere real instead of on None.
    """
    chosen = sget_int("active_feed_id")
    row = feed(chosen) if chosen else None
    if row is None:
        row = q1("SELECT * FROM feeds ORDER BY id LIMIT 1")
        if row is not None:
            sset("active_feed_id", row["id"])
    return row


def set_active_feed(feed_id: int) -> None:
    sset("active_feed_id", feed_id)
