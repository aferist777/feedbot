"""Where a long job says what it is doing.

Kept in the settings table rather than in memory, because two processes look at
it: the worker writes, the panel reads. A sweep that dies leaves its line
behind, so every reader also gets told when it started.
"""
import json
from typing import Optional

from app.db.repo import now, sdel, sget, sset

KEY = "progress:"


def start(feed_id: int, text: str = "начинаю") -> None:
    sset(KEY + str(feed_id),
         json.dumps({"text": text, "since": now()}, ensure_ascii=False))


def set_text(feed_id: int, text: str) -> None:
    current = get(feed_id)
    since = current.get("since") if current else now()
    sset(KEY + str(feed_id),
         json.dumps({"text": text, "since": since}, ensure_ascii=False))


def get(feed_id: int) -> Optional[dict]:
    raw = sget(KEY + str(feed_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def clear(feed_id: int) -> None:
    sdel(KEY + str(feed_id))
