"""Sources and the subscriptions that point feeds at them.

A source is global: one subreddit is fetched once, however many feeds watch it.
What belongs to a feed is the subscription — which source, with which words,
and how much it has actually brought in.
"""
import json
import sqlite3
from typing import Any, Optional, Sequence

from app.db.base import q, q1, x
from app.db.repo import now


def _words(raw: Optional[str]) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(word).strip() for word in value if str(word).strip()]


# ------------------------------------------------------------------ sources


def find_source(adapter: str, name: str) -> Optional[sqlite3.Row]:
    return q1("SELECT * FROM sources WHERE adapter=? AND name=?", adapter, name)


def ensure_source(adapter: str, name: str, config: Optional[dict] = None) -> int:
    """Get the id of this source, creating it the first time anyone asks."""
    row = find_source(adapter, name)
    if row is not None:
        return row["id"]
    return x(
        "INSERT INTO sources(adapter, name, config_json, created_at) VALUES(?, ?, ?, ?)",
        adapter, name, json.dumps(config or {}, ensure_ascii=False), now(),
    )


def drop_orphan_sources() -> int:
    """A source nobody subscribes to is dead weight — and its raw items go with
    it, which is why this only ever runs on sources no feed points at."""
    return x("DELETE FROM sources WHERE id NOT IN (SELECT source_id FROM feed_sources)")


# ------------------------------------------------------------ subscriptions


def subscriptions(feed_id: int) -> Sequence[sqlite3.Row]:
    return q(
        "SELECT fs.*, s.adapter, s.name, s.config_json, s.last_error "
        "FROM feed_sources fs JOIN sources s ON s.id = fs.source_id "
        "WHERE fs.feed_id=? ORDER BY s.adapter, s.name",
        feed_id,
    )


def subscription(sub_id: int) -> Optional[sqlite3.Row]:
    return q1(
        "SELECT fs.*, s.adapter, s.name FROM feed_sources fs "
        "JOIN sources s ON s.id = fs.source_id WHERE fs.id=?",
        sub_id,
    )


def subscribe(feed_id: int, source_id: int, queries: Optional[list[str]] = None) -> int:
    existing = q1(
        "SELECT id FROM feed_sources WHERE feed_id=? AND source_id=?", feed_id, source_id
    )
    if existing is not None:
        return existing["id"]
    return x(
        "INSERT INTO feed_sources(feed_id, source_id, queries_json, created_at) "
        "VALUES(?, ?, ?, ?)",
        feed_id, source_id, json.dumps(queries or [], ensure_ascii=False), now(),
    )


def update_subscription(
    sub_id: int, queries: list[str], enabled: bool, limit_posts: int
) -> None:
    x(
        "UPDATE feed_sources SET queries_json=?, enabled=?, limit_posts=? WHERE id=?",
        json.dumps(queries, ensure_ascii=False), 1 if enabled else 0, limit_posts, sub_id,
    )


def unsubscribe(sub_id: int) -> None:
    x("DELETE FROM feed_sources WHERE id=?", sub_id)
    drop_orphan_sources()


# ------------------------------------------------------------------ catalog


def catalog(feed_id: int) -> Sequence[sqlite3.Row]:
    """Sources other feeds already collect, that this one does not.

    Subscribing to one of these costs nothing and starts with history already
    in the pool — which is the whole point of sources being global.
    """
    return q(
        "SELECT s.*, ("
        "  SELECT COUNT(*) FROM raw_items ri WHERE ri.source_id = s.id"
        ") AS items FROM sources s "
        "WHERE s.id NOT IN (SELECT source_id FROM feed_sources WHERE feed_id=?) "
        "ORDER BY items DESC, s.name",
        feed_id,
    )


# ------------------------------------------------------------------ payload


def _config(raw: Optional[str]) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def payload(feed_id: int) -> dict:
    subs = []
    for row in subscriptions(feed_id):
        config = _config(row["config_json"])
        subs.append({
            "id": row["id"],
            "adapter": row["adapter"],
            "name": row["name"],
            "queries": _words(row["queries_json"]),
            "limit_posts": row["limit_posts"],
            "enabled": bool(row["enabled"]),
            "stored": row["stored_total"],
            "kept": row["kept_total"],
            "last_run_at": row["last_run_at"],
            "error": row["last_error"],
            "about": config.get("about") or config.get("title") or "",
            "subscribers": config.get("subscribers") or 0,
        })
    shelf = [
        {
            "id": row["id"],
            "adapter": row["adapter"],
            "name": row["name"],
            "items": row["items"],
        }
        for row in catalog(feed_id)
    ]
    return {"subs": subs, "catalog": shelf}
