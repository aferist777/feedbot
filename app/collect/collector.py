"""One sweep: walk a feed's subscriptions, fill the shared pool, rank what came.

Everything here is synchronous on purpose — it runs inside a worker thread so
the event loop, and with it the bot, stays free while the network waits.
"""
import json
import logging
import time
from typing import Callable, Optional

from app.collect import reddit
from app.db.base import q, q1, x
from app.db.repo import now
from app.db.sources import subscriptions

log = logging.getLogger("feedbot.collect")

Report = Callable[[str], None]


def _store_item(source_id: int, feed_id: int, item: dict) -> bool:
    """Put one post in the pool and in front of the feed. True when it is new
    to this feed — which is not the same as new to the pool, because another
    feed may have fetched it already."""
    x(
        "INSERT OR IGNORE INTO raw_items"
        "(source_id, ext_id, url, title, body, author, score, comments,"
        " created_utc, fetched_at, matched, image_url) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        source_id, item["ext_id"], item["url"], item["title"], item["body"],
        item["author"], item["score"], item["comments"], item["created_utc"],
        now(), item["matched"], item.get("image_url"),
    )
    row = q1(
        "SELECT id FROM raw_items WHERE source_id=? AND ext_id=?",
        source_id, item["ext_id"],
    )
    if row is None:
        return False
    # The pool is shared, so a post that is old news to one feed can be brand
    # new to another. Counters follow the feed, not the pool.
    before = q1(
        "SELECT id FROM feed_items WHERE feed_id=? AND raw_item_id=?", feed_id, row["id"]
    )
    if before is not None:
        return False
    x(
        "INSERT INTO feed_items(feed_id, raw_item_id, created_at) VALUES(?,?,?)",
        feed_id, row["id"], now(),
    )
    return True


def sweep(feed_id: int, report: Optional[Report] = None) -> dict:
    """Fetch every enabled subscription of one feed. Returns what it did."""
    say = report or (lambda _text: None)
    feed = q1("SELECT * FROM feeds WHERE id=?", feed_id)
    if feed is None:
        raise ValueError("нет такой ленты")

    # Old enough to have been voted on, young enough to still be a topic.
    before = now() - feed["hold_days"] * 86400
    after = now() - feed["window_days"] * 86400

    subs = [row for row in subscriptions(feed_id) if row["enabled"]]
    if not subs:
        return {"sources": 0, "fetched": 0, "fresh": 0}

    fetched = fresh = 0
    for index, sub in enumerate(subs, 1):
        name = sub["name"]
        say(f"{index}/{len(subs)} · r/{name}")
        try:
            words = json.loads(sub["queries_json"] or "[]")
        except json.JSONDecodeError:
            words = []

        started = time.time()
        try:
            items = reddit.fetch(name, sub["limit_posts"], after, before, words)
        except Exception as exc:  # one bad source must not end the sweep
            log.warning("r/%s failed: %s", name, exc)
            x("UPDATE sources SET last_error=?, last_run_at=? WHERE id=?",
              str(exc)[:500], now(), sub["source_id"])
            continue

        added = sum(_store_item(sub["source_id"], feed_id, item) for item in items)
        fetched += len(items)
        fresh += added

        x("UPDATE sources SET last_run_at=?, last_error=NULL, stored_total=stored_total+? "
          "WHERE id=?", now(), len(items), sub["source_id"])
        x("UPDATE feed_sources SET last_run_at=?, stored_total=stored_total+?, "
          "kept_total=kept_total+? WHERE id=?", now(), len(items), added, sub["id"])
        log.info("r/%s: %s posts, %s new to the feed, %.1fs",
                 name, len(items), added, time.time() - started)

    return {"sources": len(subs), "fetched": fetched, "fresh": fresh}


# ------------------------------------------------------------------ ranking


def _percentiles(values: list[float]) -> dict[float, float]:
    """Value -> its place in the pack, 0..1. Ties share a place.

    Percentile rather than the raw number because Reddit scores are a long
    tail: a post with 40 points is exceptional in one subreddit and invisible
    in another, and the feed mixes them.
    """
    ordered = sorted(set(values))
    if len(ordered) < 2:
        return {value: 1.0 for value in ordered}
    span = len(ordered) - 1
    return {value: index / span for index, value in enumerate(ordered)}


def rank_unrated(feed_id: int) -> int:
    """Give every unrated item of this feed its hot/talk place. Returns how many."""
    rows = q(
        "SELECT fi.id, ri.score, ri.comments FROM feed_items fi "
        "JOIN raw_items ri ON ri.id = fi.raw_item_id "
        "WHERE fi.feed_id=? AND fi.state='new'",
        feed_id,
    )
    if not rows:
        return 0
    hot = _percentiles([float(r["score"] or 0) for r in rows])
    talk = _percentiles([float(r["comments"] or 0) for r in rows])
    for row in rows:
        h = hot.get(float(row["score"] or 0), 0.0)
        t = talk.get(float(row["comments"] or 0), 0.0)
        # Without the model's opinion yet, rank is what the numbers say.
        x("UPDATE feed_items SET hot=?, talk=?, rank=? WHERE id=?",
          h, t, round((h * 0.6 + t * 0.4) * 100, 1), row["id"])
    return len(rows)
