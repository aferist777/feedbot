"""The job table, as plain functions.

Handlers never do slow work themselves — they enqueue and return, so the bot
keeps answering while a sweep or a render is going on.
"""
import json
import sqlite3
import time
from typing import Any, Optional

from app.db.base import q1, x

RETRY_DELAYS = [15, 60, 300]  # seconds, one per attempt


def reclaim_orphans() -> int:
    """A job that was running when the process died would stay running forever,
    because claim() only ever looks at queued rows. Put them back on startup."""
    row = q1("SELECT COUNT(*) AS n FROM jobs WHERE status='running'")
    count = row["n"] if row else 0
    if count:
        x("UPDATE jobs SET status='queued', run_after=? WHERE status='running'",
          int(time.time()) + 5)
    return count


def enqueue(
    kind: str,
    payload: Optional[dict] = None,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
) -> int:
    return x(
        "INSERT INTO jobs(kind, payload_json, status, chat_id, message_id, created_at) "
        "VALUES(?, ?, 'queued', ?, ?, ?)",
        kind,
        json.dumps(payload or {}, ensure_ascii=False),
        chat_id,
        message_id,
        int(time.time()),
    )


def claim(kinds: Optional[set] = None, exclude: Optional[set] = None) -> Optional[sqlite3.Row]:
    """Take the oldest runnable job and mark it running.

    The filters exist so a second, light lane can be added later without
    touching this: a quick job must not wait behind an hour-long sweep. The
    SELECT and the UPDATE have no await between them, so two lanes can never
    grab the same row.
    """
    where = "status='queued' AND (run_after IS NULL OR run_after <= ?)"
    args: list = [int(time.time())]
    if kinds:
        where += " AND kind IN (%s)" % ",".join("?" * len(kinds))
        args += sorted(kinds)
    if exclude:
        where += " AND kind NOT IN (%s)" % ",".join("?" * len(exclude))
        args += sorted(exclude)
    row = q1(f"SELECT * FROM jobs WHERE {where} ORDER BY id LIMIT 1", *args)
    if row is None:
        return None
    x("UPDATE jobs SET status='running', started_at=?, attempts=attempts+1 WHERE id=?",
      int(time.time()), row["id"])
    return q1("SELECT * FROM jobs WHERE id=?", row["id"])


def finish(job_id: int) -> None:
    x("UPDATE jobs SET status='done', finished_at=?, error=NULL WHERE id=?",
      int(time.time()), job_id)


def fail(job_id: int, attempts: int, error: str) -> bool:
    """Reschedule with a growing delay, or give up. True when it will retry."""
    error = error[:2000]
    if attempts <= len(RETRY_DELAYS):
        x("UPDATE jobs SET status='queued', run_after=?, error=? WHERE id=?",
          int(time.time()) + RETRY_DELAYS[attempts - 1], error, job_id)
        return True
    x("UPDATE jobs SET status='failed', finished_at=?, error=? WHERE id=?",
      int(time.time()), error, job_id)
    return False


def payload_of(row: sqlite3.Row) -> dict[str, Any]:
    try:
        return json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        return {}
