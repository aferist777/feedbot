"""The panel's HTTP side: an aiohttp server inside the bot's own process.

It binds to the loopback address and refuses anything that did not come from
this machine. That is the whole authentication story, and it is why keys are
handed out one at a time rather than baked into the page.

The window that displays this lives in a separate process — see window.py.
"""
import asyncio
import json
import logging
import time
import webbrowser
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from app.config import PANEL_HOST, PANEL_PORT, PANEL_URL
from app.db.repo import (
    active_feed, create_feed, feed, feeds, sdel, set_active_feed, sset,
)
from app.db import sources
from app.db.base import q, q1, x
from app.collect import registry
from app.reel import script as reel_script
from app.reel import packs as reel_packs
from app.reel import render as reel_render
from app.reel import theme as reel_theme
from app.reel import voice as reel_voice
from app.treat import registry as treats
from app.jobs import progress, queue
from app.llm import client as llm, models as llm_models
from app.panel import keys

log = logging.getLogger("feedbot.panel")

STATIC = Path(__file__).parent / "static"
LOOPBACK = ("127.0.0.1", "::1", "localhost")

_runner: web.AppRunner | None = None

# Set by the bot once it is actually polling. The panel cannot read this off
# app.config, because on a first run the token arrives through the panel itself
# and config was already read at import.
_bot_username: str | None = None


def set_bot(username: str) -> None:
    global _bot_username
    _bot_username = username


@web.middleware
async def only_local(request: web.Request, handler: Any) -> web.StreamResponse:
    if (request.remote or "") not in LOOPBACK:
        log.warning("refused %s — the panel is for this machine only", request.remote)
        raise web.HTTPForbidden(text="панель доступна только с этой машины")
    return await handler(request)


async def _body(request: web.Request) -> dict:
    try:
        return await request.json()
    except (json.JSONDecodeError, ValueError):
        return {}


# ------------------------------------------------------------------- static


def _file(name: str, content_type: str):
    async def handler(request: web.Request) -> web.Response:
        return web.Response(
            body=(STATIC / name).read_bytes(),
            content_type=content_type,
            charset="utf-8",
        )

    return handler


# -------------------------------------------------------------------- state


def _feeds_payload() -> list[dict]:
    active = active_feed()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "note": row["note"] or "",
            "window_days": row["window_days"],
            "hold_days": row["hold_days"],
            "reel_seconds": row["reel_seconds"],
            "voice": row["voice"],
            "voice_tempo": row["voice_tempo"],
            "pack": row["pack"],
            "sources": q1(
                "SELECT COUNT(*) AS n FROM feed_sources WHERE feed_id=?", row["id"]
            )["n"],
            "active": bool(active and active["id"] == row["id"]),
        }
        for row in feeds()
    ]


async def get_state(request: web.Request) -> web.Response:
    """Everything the window needs to draw itself once."""
    return web.json_response({
        "keys": keys.payload(),
        "feeds": _feeds_payload(),
        # A token exists but the bot has not reported in yet: it is starting.
        "token_pending": bool(keys.value("tg")) and _bot_username is None,
        "bot_running": _bot_username is not None,
        "bot_username": _bot_username,
        "adapters": registry.payload(),
        "modes": treats.payload(),
        "voices": [{"id": vid, "label": label} for vid, label in reel_voice.VOICES],
    })


# --------------------------------------------------------------------- keys


async def key_set(request: web.Request) -> web.Response:
    data = await _body(request)
    key_id = data.get("id", "")
    if key_id not in keys.BY_ID:
        raise web.HTTPNotFound(text="нет такого ключа")
    raw = str(data.get("value") or "")
    ok, note = await keys.check(key_id, raw)
    if not ok:
        return web.json_response({"ok": False, "note": note})
    keys.save(key_id, raw)
    log.info("key %s saved (%s)", key_id, note)
    return web.json_response({"ok": True, "note": note, "mask": keys.mask(raw.strip())})


async def key_reveal(request: web.Request) -> web.Response:
    """One key, asked for explicitly. Nothing here is ever sent with the page."""
    key_id = (await _body(request)).get("id", "")
    if key_id not in keys.BY_ID:
        raise web.HTTPNotFound(text="нет такого ключа")
    log.info("key %s revealed", key_id)
    return web.json_response({"value": keys.value(key_id)})


async def key_clear(request: web.Request) -> web.Response:
    key_id = (await _body(request)).get("id", "")
    if key_id not in keys.BY_ID:
        raise web.HTTPNotFound(text="нет такого ключа")
    keys.clear(key_id)
    return web.json_response({"ok": True})


async def key_check(request: web.Request) -> web.Response:
    data = await _body(request)
    key_id = data.get("id", "")
    if key_id not in keys.BY_ID:
        raise web.HTTPNotFound(text="нет такого ключа")
    raw = str(data.get("value") or "") or keys.value(key_id)
    ok, note = await keys.check(key_id, raw)
    return web.json_response({"ok": ok, "note": note})


# -------------------------------------------------------------------- feeds


async def feed_create(request: web.Request) -> web.Response:
    data = await _body(request)
    name = str(data.get("name") or "").strip()
    if not name:
        raise web.HTTPBadRequest(text="лента без имени")
    if q1("SELECT id FROM feeds WHERE name=?", name):
        raise web.HTTPBadRequest(text="лента с таким именем уже есть")
    feed_id = create_feed(name, str(data.get("note") or ""))
    set_active_feed(feed_id)
    return web.json_response({"id": feed_id, "feeds": _feeds_payload()})


async def feed_update(request: web.Request) -> web.Response:
    data = await _body(request)
    row = feed(int(data.get("id") or 0))
    if row is None:
        raise web.HTTPNotFound(text="нет такой ленты")
    def _days(field: str, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(data.get(field, row[field]))))
        except (TypeError, ValueError):
            return row[field]

    window = _days("window_days", 2, 365)
    hold = _days("hold_days", 0, 90)
    if hold >= window:
        raise web.HTTPBadRequest(text="выдержка должна быть меньше окна")
    try:
        seconds = max(15, min(600, int(data.get("reel_seconds", row["reel_seconds"]))))
    except (TypeError, ValueError):
        seconds = row["reel_seconds"]
    try:
        tempo = max(0.5, min(2.0, float(data.get("voice_tempo", row["voice_tempo"]))))
    except (TypeError, ValueError):
        tempo = row["voice_tempo"]
    x("UPDATE feeds SET name=?, note=?, window_days=?, hold_days=?, reel_seconds=?, "
      "voice=?, voice_tempo=? WHERE id=?",
      str(data.get("name") or row["name"]).strip(),
      str(data.get("note") or ""), window, hold, seconds,
      str(data.get("voice") or row["voice"]), tempo, row["id"])
    return web.json_response({"feeds": _feeds_payload()})


async def feed_activate(request: web.Request) -> web.Response:
    row = feed(int((await _body(request)).get("id") or 0))
    if row is None:
        raise web.HTTPNotFound(text="нет такой ленты")
    set_active_feed(row["id"])
    return web.json_response({"feeds": _feeds_payload()})


async def feed_delete(request: web.Request) -> web.Response:
    """The window asks twice before calling this; the server does not ask again."""
    row = feed(int((await _body(request)).get("id") or 0))
    if row is None:
        raise web.HTTPNotFound(text="нет такой ленты")
    x("DELETE FROM feeds WHERE id=?", row["id"])
    sset("active_feed_id", "")
    active_feed()  # picks the next one that exists, if any
    log.info("feed %s deleted", row["name"])
    return web.json_response({"feeds": _feeds_payload()})


# ------------------------------------------------------------------ sources


def _require_feed() -> int:
    row = active_feed()
    if row is None:
        raise web.HTTPBadRequest(text="сначала заведи ленту")
    return row["id"]


async def sources_state(request: web.Request) -> web.Response:
    return web.json_response(sources.payload(_require_feed()))


async def source_lookup(request: web.Request) -> web.Response:
    """Ask the service whether this name is real, before anything is saved."""
    data = await _body(request)
    adapter = registry.BY_ID.get(str(data.get("adapter") or ""))
    if adapter is None:
        raise web.HTTPNotFound(text="нет такого адаптера")
    if adapter.look_up is None:
        return web.json_response({"ok": True, "info": None})
    # httpx here is synchronous and the bot shares this event loop, so a
    # two-second lookup would freeze the bot with it.
    info = await asyncio.to_thread(adapter.look_up, str(data.get("name") or ""))
    if info is None:
        return web.json_response({"ok": False, "note": "не нашёл такой источник"})
    return web.json_response({"ok": True, "info": info})


async def source_add(request: web.Request) -> web.Response:
    data = await _body(request)
    feed_id = _require_feed()
    adapter = registry.BY_ID.get(str(data.get("adapter") or ""))
    if adapter is None:
        raise web.HTTPNotFound(text="нет такого адаптера")

    info = None
    name = str(data.get("name") or "").strip()
    if adapter.look_up is not None:
        info = await asyncio.to_thread(adapter.look_up, name)
        if info is None:
            return web.json_response({"ok": False, "note": "не нашёл такой источник"})
        name = info["name"]  # canonical spelling, so r/saas and r/SaaS are one source

    source_id = sources.ensure_source(adapter.id, name, info)
    sources.subscribe(feed_id, source_id, list(data.get("queries") or []))
    log.info("feed %s subscribed to %s/%s", feed_id, adapter.id, name)
    return web.json_response({"ok": True, **sources.payload(feed_id)})


async def source_subscribe(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    source_id = int((await _body(request)).get("source_id") or 0)
    if q1("SELECT id FROM sources WHERE id=?", source_id) is None:
        raise web.HTTPNotFound(text="нет такого источника")
    sources.subscribe(feed_id, source_id)
    return web.json_response(sources.payload(feed_id))


async def source_update(request: web.Request) -> web.Response:
    data = await _body(request)
    feed_id = _require_feed()
    sub = sources.subscription(int(data.get("id") or 0))
    if sub is None:
        raise web.HTTPNotFound(text="нет такой подписки")
    words = [str(w).strip() for w in (data.get("queries") or []) if str(w).strip()]
    try:
        want = max(1, min(1000, int(data.get("limit_posts", sub["limit_posts"]))))
    except (TypeError, ValueError):
        want = sub["limit_posts"]
    sources.update_subscription(sub["id"], words, bool(data.get("enabled", True)), want)
    return web.json_response(sources.payload(feed_id))


async def source_remove(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    sub = sources.subscription(int((await _body(request)).get("id") or 0))
    if sub is None:
        raise web.HTTPNotFound(text="нет такой подписки")
    sources.unsubscribe(sub["id"])
    log.info("feed %s dropped %s/%s", feed_id, sub["adapter"], sub["name"])
    return web.json_response(sources.payload(feed_id))


# -------------------------------------------------------------------- sweep


def _running(feed_id: int) -> bool:
    row = q1(
        "SELECT id FROM jobs WHERE kind='collect.run' AND status IN ('queued','running') "
        "AND payload_json LIKE ?",
        f'%"feed_id": {feed_id}%',
    )
    return row is not None


async def sweep_start(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    if _running(feed_id):
        return web.json_response({"ok": False, "note": "сбор уже идёт"})
    queue.enqueue("collect.run", {"feed_id": feed_id})
    return web.json_response({"ok": True})


async def sweep_state(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    return web.json_response({
        "running": _running(feed_id),
        "progress": progress.get(feed_id),
    })


# -------------------------------------------------------------------- items


def _title(title: Optional[str], body: Optional[str]) -> str:
    """What to show when a moderator took the title but left the post."""
    if title:
        return title
    first = (body or "").strip().splitlines()[0] if (body or "").strip() else ""
    return (first[:90] + "…") if len(first) > 90 else (first or "(без заголовка)")


async def items_state(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    state = request.query.get("state") or "new"
    rows = q(
        "SELECT fi.id, fi.hot, fi.talk, fi.interesting, fi.why, fi.rank, fi.state, "
        "ri.title, ri.body, ri.url, ri.score, ri.comments, ri.created_utc, s.name AS source "
        "FROM feed_items fi "
        "JOIN raw_items ri ON ri.id = fi.raw_item_id "
        "JOIN sources s ON s.id = ri.source_id "
        "WHERE fi.feed_id=? AND fi.state=? ORDER BY fi.rank DESC LIMIT 120",
        feed_id, state,
    )
    made: dict[int, list[str]] = {}
    for row in q("SELECT feed_item_id, mode FROM treatments"):
        made.setdefault(row["feed_item_id"], []).append(row["mode"])
    working = {
        int(json.loads(row["payload_json"]).get("item_id") or 0)
        for row in q("SELECT payload_json FROM jobs WHERE kind IN "
                     "('treat.run','script.run','voice.run','render.run') "
                     "AND status IN ('queued','running')")
    }
    scripted = {row["feed_item_id"] for row in q("SELECT feed_item_id FROM scripts")}
    voiced = {row["feed_item_id"] for row in q("SELECT feed_item_id FROM voiceovers")}
    reeled = {row["feed_item_id"] for row in q("SELECT feed_item_id FROM reels")}
    counts = {
        row["state"]: row["n"]
        for row in q(
            "SELECT state, COUNT(*) AS n FROM feed_items WHERE feed_id=? GROUP BY state",
            feed_id,
        )
    }
    return web.json_response({
        "items": [{
            "id": row["id"],
            "title": _title(row["title"], row["body"]),
            "body": (row["body"] or "")[:400],
            "url": row["url"],
            "source": row["source"],
            "score": row["score"],
            "comments": row["comments"],
            "hot": row["hot"],
            "talk": row["talk"],
            "interesting": row["interesting"],
            "why": row["why"],
            "rank": row["rank"],
            "age_days": round((time.time() - (row["created_utc"] or 0)) / 86400, 1),
            "made": made.get(row["id"], []),
            "scripted": row["id"] in scripted,
            "voiced": row["id"] in voiced,
            "reeled": row["id"] in reeled,
            "working": row["id"] in working,
        } for row in rows],
        "counts": counts,
    })


async def open_link(request: web.Request) -> web.Response:
    """Open a post in the real browser.

    The panel is a webview window: a plain link would replace the panel with
    Reddit and leave no way back, since the window has no address bar.
    """
    url = str((await _body(request)).get("url") or "")
    if not url.startswith(("http://", "https://")):
        raise web.HTTPBadRequest(text="это не ссылка")
    webbrowser.open(url)
    return web.json_response({"ok": True})


async def item_state(request: web.Request) -> web.Response:
    data = await _body(request)
    state = str(data.get("state") or "")
    if state not in ("new", "picked", "hidden", "used"):
        raise web.HTTPBadRequest(text="неизвестное состояние")
    x("UPDATE feed_items SET state=? WHERE id=?", state, int(data.get("id") or 0))
    return web.json_response({"ok": True})


# ------------------------------------------------------------------- treat


async def treat_start(request: web.Request) -> web.Response:
    data = await _body(request)
    item_id = int(data.get("item_id") or 0)
    mode = str(data.get("mode") or "retell")
    if mode not in treats.BY_ID:
        raise web.HTTPNotFound(text="нет такой обработки")
    if q1("SELECT id FROM feed_items WHERE id=?", item_id) is None:
        raise web.HTTPNotFound(text="нет такого поста")
    queue.enqueue("treat.run", {"item_id": item_id, "mode": mode})
    return web.json_response({"ok": True})


async def treat_read(request: web.Request) -> web.Response:
    row = q1(
        "SELECT * FROM treatments WHERE feed_item_id=? AND mode=?",
        int(request.query.get("item_id") or 0),
        request.query.get("mode") or "retell",
    )
    if row is None:
        return web.json_response({"found": False})
    return web.json_response({
        "found": True,
        "title": row["title"],
        "hook": row["hook"],
        "text": row["text"],
        "model": row["model"],
    })


# ------------------------------------------------------------------ script


async def script_start(request: web.Request) -> web.Response:
    item_id = int((await _body(request)).get("item_id") or 0)
    if q1("SELECT id FROM treatments WHERE feed_item_id=?", item_id) is None:
        return web.json_response(
            {"ok": False, "note": "сначала пересказ — сценарий пишется из него"})
    queue.enqueue("script.run", {"item_id": item_id, "mode": "retell"})
    return web.json_response({"ok": True})


async def script_read(request: web.Request) -> web.Response:
    made = reel_script.read(int(request.query.get("item_id") or 0))
    if made is None:
        return web.json_response({"found": False})
    return web.json_response({"found": True, **made})


# ------------------------------------------------------------------- voice


async def voice_start(request: web.Request) -> web.Response:
    item_id = int((await _body(request)).get("item_id") or 0)
    if q1("SELECT id FROM scripts WHERE feed_item_id=?", item_id) is None:
        return web.json_response({"ok": False, "note": "сначала сценарий"})
    queue.enqueue("voice.run", {"item_id": item_id})
    return web.json_response({"ok": True})


async def voice_read(request: web.Request) -> web.Response:
    made = reel_voice.read(int(request.query.get("item_id") or 0))
    if made is None:
        return web.json_response({"found": False})
    return web.json_response({
        "found": True,
        "seconds": made["seconds"],
        "voice": made["voice"],
        "words": len(made["words"]),
        "preview": made["words"][:12],
    })


async def voice_file(request: web.Request) -> web.StreamResponse:
    """The mp3 itself, so the window can play it back."""
    made = reel_voice.read(int(request.query.get("item_id") or 0))
    if made is None:
        raise web.HTTPNotFound(text="нет озвучки")
    path = Path(made["path"])
    if not path.exists():
        raise web.HTTPNotFound(text="файл пропал")
    return web.FileResponse(path, headers={"Content-Type": "audio/mpeg"})


async def voices_list(request: web.Request) -> web.Response:
    return web.json_response({"voices": [
        {"id": vid, "label": label} for vid, label in reel_voice.VOICES
    ]})


# ------------------------------------------------------------------ models


async def models_state(request: web.Request) -> web.Response:
    return web.json_response({"fields": llm_models.payload()})


async def models_set(request: web.Request) -> web.Response:
    data = await _body(request)
    key = str(data.get("key") or "")
    if key not in llm_models.BY_KEY:
        raise web.HTTPNotFound(text="нет такого поля")
    try:
        value = llm_models.cast(key, data.get("value"))
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"не подходит: {exc}")
    sset(key, value)
    return web.json_response({"fields": llm_models.payload()})


async def models_reset(request: web.Request) -> web.Response:
    key = str((await _body(request)).get("key") or "")
    if key not in llm_models.BY_KEY:
        raise web.HTTPNotFound(text="нет такого поля")
    sdel(key)
    return web.json_response({"fields": llm_models.payload()})


async def models_check(request: web.Request) -> web.Response:
    """A real request to the model that is set, so a typo in its name shows up
    here rather than in the middle of a sweep."""
    name = str((await _body(request)).get("model") or "") or llm_models.write_model()
    started = time.time()
    try:
        answer = await asyncio.to_thread(
            llm.ask, name,
            [{"role": "user", "content": "Ответь одним словом: работает?"}],
            None, 200, 0.0,
        )
    except llm.LLMError as exc:
        return web.json_response({"ok": False, "note": str(exc)[:200]})
    return web.json_response({
        "ok": True,
        "note": f"{time.time() - started:.1f} с · {str(answer).strip()[:60]}",
    })


# --------------------------------------------------------------------- look


async def theme_state(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    row = feed(feed_id)
    engine_ok, engine_note = reel_render.ready()
    return web.json_response({
        "fields": reel_theme.payload(feed_id),
        "packs": reel_packs.payload(),
        "pack": row["pack"],
        "engine": {"ok": engine_ok, "note": engine_note},
    })


async def theme_set(request: web.Request) -> web.Response:
    data = await _body(request)
    feed_id = _require_feed()
    try:
        reel_theme.write(feed_id, str(data.get("key") or ""), data.get("value"))
    except KeyError:
        raise web.HTTPNotFound(text="нет такого поля")
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"не подходит: {exc}")
    return web.json_response({"fields": reel_theme.payload(feed_id)})


async def theme_reset(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    key = (await _body(request)).get("key")
    reel_theme.reset(feed_id, str(key) if key else None)
    return web.json_response({"fields": reel_theme.payload(feed_id)})


async def pack_set(request: web.Request) -> web.Response:
    feed_id = _require_feed()
    pack = str((await _body(request)).get("pack") or "")
    chosen = reel_packs.BY_ID.get(pack)
    if chosen is None:
        raise web.HTTPNotFound(text="нет такого пакета")
    if not chosen.ready:
        return web.json_response({"ok": False, "note": "этот пакет ещё не собран"})
    x("UPDATE feeds SET pack=? WHERE id=?", pack, feed_id)
    return web.json_response({"ok": True, "pack": pack})


# ------------------------------------------------------------------- render


async def render_start(request: web.Request) -> web.Response:
    item_id = int((await _body(request)).get("item_id") or 0)
    if q1("SELECT id FROM voiceovers WHERE feed_item_id=?", item_id) is None:
        return web.json_response({"ok": False, "note": "сначала озвучка"})
    ok, note = reel_render.ready()
    if not ok:
        return web.json_response({"ok": False, "note": note})
    queue.enqueue("render.run", {"item_id": item_id})
    return web.json_response({"ok": True})


async def render_read(request: web.Request) -> web.Response:
    item_id = int(request.query.get("item_id") or 0)
    made = reel_render.read(item_id)
    if made is None:
        return web.json_response({"found": False, "progress": progress.get(item_id)})
    return web.json_response({
        "found": True,
        "seconds": made["seconds"],
        "size": made["size"],
        "pack": made["pack"],
        "progress": progress.get(item_id),
    })


async def render_file(request: web.Request) -> web.StreamResponse:
    made = reel_render.read(int(request.query.get("item_id") or 0))
    if made is None:
        raise web.HTTPNotFound(text="нет ролика")
    path = Path(made["path"])
    if not path.exists():
        raise web.HTTPNotFound(text="файл пропал")
    return web.FileResponse(path, headers={"Content-Type": "video/mp4"})


# ------------------------------------------------------------------ run/stop


def build_app() -> web.Application:
    app = web.Application(middlewares=[only_local])
    app.router.add_get("/", _file("index.html", "text/html"))
    app.router.add_get("/app.css", _file("app.css", "text/css"))
    app.router.add_get("/app.js", _file("app.js", "application/javascript"))

    app.router.add_get("/api/state", get_state)
    app.router.add_post("/api/keys/set", key_set)
    app.router.add_post("/api/keys/reveal", key_reveal)
    app.router.add_post("/api/keys/clear", key_clear)
    app.router.add_post("/api/keys/check", key_check)
    app.router.add_post("/api/feeds/create", feed_create)
    app.router.add_post("/api/feeds/update", feed_update)
    app.router.add_post("/api/feeds/activate", feed_activate)
    app.router.add_post("/api/feeds/delete", feed_delete)
    app.router.add_get("/api/sources", sources_state)
    app.router.add_post("/api/sources/lookup", source_lookup)
    app.router.add_post("/api/sources/add", source_add)
    app.router.add_post("/api/sources/subscribe", source_subscribe)
    app.router.add_post("/api/sources/update", source_update)
    app.router.add_post("/api/sources/remove", source_remove)
    app.router.add_post("/api/sweep", sweep_start)
    app.router.add_get("/api/sweep", sweep_state)
    app.router.add_get("/api/items", items_state)
    app.router.add_post("/api/items/state", item_state)
    app.router.add_post("/api/open", open_link)
    app.router.add_post("/api/treat", treat_start)
    app.router.add_get("/api/treat", treat_read)
    app.router.add_post("/api/script", script_start)
    app.router.add_get("/api/script", script_read)
    app.router.add_post("/api/voice", voice_start)
    app.router.add_get("/api/voice", voice_read)
    app.router.add_get("/api/voice/file", voice_file)
    app.router.add_get("/api/voices", voices_list)
    app.router.add_get("/api/models", models_state)
    app.router.add_post("/api/models/set", models_set)
    app.router.add_post("/api/models/reset", models_reset)
    app.router.add_post("/api/models/check", models_check)
    app.router.add_get("/api/theme", theme_state)
    app.router.add_post("/api/theme/set", theme_set)
    app.router.add_post("/api/theme/reset", theme_reset)
    app.router.add_post("/api/pack", pack_set)
    app.router.add_post("/api/render", render_start)
    app.router.add_get("/api/render", render_read)
    app.router.add_get("/api/render/file", render_file)
    return app


async def start() -> str:
    global _runner
    _runner = web.AppRunner(build_app(), access_log=None)
    await _runner.setup()
    site = web.TCPSite(_runner, PANEL_HOST, PANEL_PORT)
    await site.start()
    log.info("panel is listening on %s", PANEL_URL)
    return PANEL_URL


async def stop() -> None:
    global _runner
    if _runner is not None:
        await _runner.cleanup()
        _runner = None
