"""One connection, shared by every thread.

sqlite3.threadsafety is 3 (serialized) on CPython, so a single connection is
safe to hand around, and it keeps the collectors — which run in worker threads
so the event loop stays free — from each opening their own file handle.
"""
import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence

from app.config import DB_PATH

_conn: Optional[sqlite3.Connection] = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # WAL so a long read never blocks a write; busy_timeout so a write that
        # arrives mid-read waits instead of raising "database is locked".
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


def _ensure_column(table: str, column: str, ddl: str) -> None:
    """schema.sql only ever creates; a column added to an existing file needs
    an ALTER. Kept next to the schema so the two are read together."""
    existing = {row["name"] for row in conn().execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn().execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn().commit()


def init_db() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    c = conn()
    c.executescript(sql)
    c.commit()
    _ensure_column("feeds", "window_days", "INTEGER NOT NULL DEFAULT 45")
    _ensure_column("feeds", "hold_days", "INTEGER NOT NULL DEFAULT 7")
    _ensure_column("feed_sources", "limit_posts", "INTEGER NOT NULL DEFAULT 60")
    _ensure_column("feeds", "reel_seconds", "INTEGER NOT NULL DEFAULT 90")
    _ensure_column("feeds", "voice", "TEXT NOT NULL DEFAULT 'ru-RU-DmitryNeural'")
    _ensure_column("feeds", "voice_tempo", "REAL NOT NULL DEFAULT 1.2")
    _ensure_column("feeds", "pack", "TEXT NOT NULL DEFAULT 'talk'")
    _ensure_column("feeds", "theme_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column("raw_items", "image_url", "TEXT")


def q(sql: str, *args: Any) -> Sequence[sqlite3.Row]:
    return conn().execute(sql, args).fetchall()


def q1(sql: str, *args: Any) -> Optional[sqlite3.Row]:
    return conn().execute(sql, args).fetchone()


def x(sql: str, *args: Any) -> int:
    cur = conn().execute(sql, args)
    conn().commit()
    return cur.lastrowid or 0
