"""Reddit through Arctic Shift — the maintained successor to Pushshift.

Reddit itself is closed to anonymous callers: the JSON endpoints, Jina Reader
and the RSS feeds all answer 403 or rate-limit to zero, and that does not
depend on the address you call from. Arctic Shift mirrors the same content,
needs no key, and is current to the day.

This module only knows how to look a subreddit up; fetching posts is the
collector's job and lands with it.
"""
import logging
import time
from typing import Any, Optional

import httpx

log = logging.getLogger("feedbot.reddit")

BASE = "https://arctic-shift.photon-reddit.com/api"
UA = "feedbot/0.1 (personal niche feed)"

# Arctic Shift throttles with both 422 ("slow down") and 429. Neither means the
# request was wrong — both mean wait. Treating 429 as fatal is a mistake that
# only shows up under a real sweep, when the calls come close together.
THROTTLED = (422, 429)
RETRY_PAUSE = 8.0


def get(path: str, **params: Any) -> Optional[list[dict]]:
    """None means the call failed; an empty list means it worked and found nothing."""
    for attempt in range(3):
        try:
            response = httpx.get(
                BASE + path, params=params, headers={"User-Agent": UA}, timeout=60
            )
        except httpx.HTTPError as exc:
            log.warning("arctic shift %s failed: %s", path, exc)
            return None
        if response.status_code in THROTTLED:
            if attempt == 2:
                log.warning("arctic shift %s: gave up after 3 tries (throttled)", path)
                return None
            time.sleep(RETRY_PAUSE * (attempt + 1))  # 8, then 16 seconds
            continue
        if response.status_code != 200:
            log.warning("arctic shift %s: %s", response.status_code, response.text[:120])
            return None
        return response.json().get("data") or []
    return None


PAGE = 100  # Arctic Shift refuses anything above this outright
PAUSE = 0.4

# Reddit leaves a tombstone rather than deleting a row, and the archive keeps
# whichever half it saw first. In practice most of what a sweep brings back has
# lost its title to a moderator while the body survives — so a dead title is
# not a reason to drop the post, and a dead body is.
DEAD_BODY = ("[removed]", "[deleted]", "")
PICTURE = (".jpg", ".jpeg", ".png", ".webp", ".gif")
DEAD_TITLE = "removed by moderator"
MIN_BODY = 40


def _image(data: dict[str, Any]) -> Optional[str]:
    """The post's own picture, when it has one.

    Two places to look: a link post pointing straight at an image, and the
    preview Reddit generates for everything else. Preview URLs arrive
    HTML-escaped, which is why the ampersands are put back.
    """
    link = (data.get("url") or "").strip()
    if link.lower().endswith(PICTURE):
        return link
    preview = ((data.get("preview") or {}).get("images") or [{}])[0]
    source = (preview.get("source") or {}).get("url") or ""
    return source.replace("&amp;", "&") if source else None


def _post(data: dict[str, Any], matched: str) -> dict[str, Any]:
    title = (data.get("title") or "").strip()
    if DEAD_TITLE in title.lower():
        title = ""  # stored empty rather than as a tombstone string
    body = (data.get("selftext") or "").strip()
    if body.lower() in DEAD_BODY:
        body = ""
    return {
        "ext_id": data.get("id") or "",
        "url": "https://www.reddit.com" + (data.get("permalink") or ""),
        "title": title,
        "body": body[:4000],
        "author": data.get("author"),
        "score": int(data.get("score") or 0),
        "comments": int(data.get("num_comments") or 0),
        "created_utc": int(data.get("created_utc") or 0),
        "matched": matched,
        "image_url": _image(data),
    }


def _page(sub: str, after: int, before: int, query: str = "") -> list[dict]:
    params: dict[str, Any] = {
        "subreddit": sub, "limit": PAGE, "sort": "desc",
        "after": after, "before": before,
    }
    if query:
        params["query"] = query
    return get("/posts/search", **params) or []


def fetch(sub: str, want: int, after: int, before: int, words: list[str]) -> list[dict]:
    """Up to `want` posts from a subreddit inside a time window.

    Arctic Shift can only sort by time and caps a page at 100, so more than
    that means walking backwards: each page ends where the next one starts.
    Words, when given, are separate searches — the pool deduplicates whatever
    they have in common.
    """
    found: dict[str, dict] = {}
    for query in words or [""]:
        cursor = before
        while len(found) < want:
            rows = _page(sub, after, cursor, query)
            if not rows:
                break
            for row in rows:
                item = _post(row, query)
                # Something to read is the bar: a title on its own is enough,
                # a body on its own is enough, a tombstone is not.
                usable = item["title"] or len(item["body"]) >= MIN_BODY
                if item["ext_id"] and usable:
                    found.setdefault(item["ext_id"], item)
            oldest = min((int(r.get("created_utc") or 0) for r in rows), default=0)
            if oldest <= after or len(rows) < PAGE:
                break  # the window is exhausted, not the page
            cursor = oldest - 1
            time.sleep(PAUSE)
        time.sleep(PAUSE)
    log.info("r/%s: %s posts", sub, len(found))
    return list(found.values())[:want]


def look_up(name: str) -> Optional[dict]:
    """What Reddit knows about a subreddit, or None if there is no such thing.

    Called before a source is saved, so a typo is caught while the person is
    still looking at the field rather than a week later in an empty sweep.
    """
    name = name.strip().lstrip("/").removeprefix("r/").strip()
    if not name:
        return None
    rows = get("/subreddits/search", subreddit=name, limit=3)
    if not rows:
        return None
    exact = next(
        (r for r in rows if (r.get("display_name") or "").lower() == name.lower()),
        None,
    )
    if exact is None:
        return None
    return {
        "name": exact.get("display_name") or name,
        "title": (exact.get("title") or "").strip(),
        "about": (exact.get("public_description") or "").strip(),
        "subscribers": int(exact.get("subscribers") or 0),
        "over18": bool(exact.get("over18")),
        "private": (exact.get("subreddit_type") or "public") != "public",
    }
