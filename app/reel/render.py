"""Handing the reel to Remotion.

Everything the composition needs travels as one props file: beats, word
timings, the theme and the name of the audio file. The React side reads
nothing off the disk itself, so what renders is exactly what was passed.
"""
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.config import DATA_DIR, ROOT
from app.db.base import q1, x
from app.db.repo import now
from app.reel import script as reel_script, theme as reel_theme, voice as reel_voice

log = logging.getLogger("feedbot.reel.render")

RENDER_DIR = ROOT / "render"
PUBLIC_DIR = RENDER_DIR / "public"
OUT_DIR = DATA_DIR / "reels"
# The CLI shipped inside the render project, so nothing depends on a global npx.
BINARY = RENDER_DIR / "node_modules" / ".bin" / "remotion.cmd"

FPS = 30
# Rendering a ninety-second reel takes minutes; this only guards against a hang.
TIMEOUT = 45 * 60


def ready() -> tuple[bool, str]:
    if not BINARY.exists():
        return False, "Remotion не установлен: запусти npm i в папке render"
    return True, "готов"


MAX_PICTURE = 8 * 1024 * 1024


def _picture(item_id: int) -> Optional[str]:
    """Fetch the post's own image into public/, and say what it is called.

    Deliberately narrow: only an image content type, only up to eight
    megabytes, and the file is never executed or parsed — it goes to an <img>
    tag and nowhere else. Anything unexpected means no picture, not an error.
    """
    row = q1(
        "SELECT ri.image_url FROM feed_items fi "
        "JOIN raw_items ri ON ri.id = fi.raw_item_id WHERE fi.id=?",
        item_id,
    )
    url = (row["image_url"] if row else "") or ""
    if not url.startswith("https://"):
        return None
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        if response.status_code != 200:
            return None
        kind = response.headers.get("content-type", "")
        if not kind.startswith("image/") or len(response.content) > MAX_PICTURE:
            return None
        suffix = {"image/png": ".png", "image/webp": ".webp",
                  "image/gif": ".gif"}.get(kind.split(";")[0], ".jpg")
        name = f"post-{item_id}{suffix}"
        (PUBLIC_DIR / name).write_bytes(response.content)
        log.info("картинка поста: %s КБ", len(response.content) // 1024)
        return name
    except httpx.HTTPError as exc:
        log.warning("картинка не скачалась: %s", exc)
        return None


def build_props(item_id: int) -> dict:
    """Collect everything into the shape render/src/types.ts describes."""
    row = q1(
        "SELECT fi.feed_id, f.pack, f.voice_tempo FROM feed_items fi "
        "JOIN feeds f ON f.id = fi.feed_id WHERE fi.id=?",
        item_id,
    )
    if row is None:
        raise ValueError("нет такого поста")
    plan = reel_script.read(item_id)
    if plan is None:
        raise ValueError("сначала сценарий")
    voiced = reel_voice.read(item_id)
    if voiced is None:
        raise ValueError("сначала озвучка")

    tempo = max(row["voice_tempo"], 0.1)
    timing = reel_voice.beat_words(item_id, plan["beats"], tempo)
    if not timing:
        raise ValueError("тайминги не легли на биты — переозвучь")

    beats = []
    for cut in timing:
        source = plan["beats"][cut["index"]]
        beats.append({
            "index": cut["index"],
            "start": cut["start"],
            "end": cut["end"],
            "on_screen": source.get("on_screen") or "",
            "scene": source.get("scene") or "line",
            "icon": source.get("icon") or "",
            "items": source.get("items") or [],
            "keys": source.get("keys") or [],
            "words": cut["words"],
        })

    # Remotion serves audio out of its own public folder, so the file is copied
    # rather than referenced where it lies.
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    audio_name = f"voice-{item_id}.mp3"
    shutil.copyfile(voiced["path"], PUBLIC_DIR / audio_name)

    # A post that came with a picture can use it — but only in a beat that
    # asked for one, and only if the file really is an image.
    picture = _picture(item_id)
    if picture:
        for beat in beats:
            if beat["scene"] == "photo":
                beat["photo"] = picture
    else:
        for beat in beats:
            if beat["scene"] == "photo":
                beat["scene"] = "line"

    return {
        "pack": row["pack"] or "talk",
        "theme": reel_theme.read(row["feed_id"]),
        "beats": beats,
        "audio": {
            "file": audio_name,
            "tempo": tempo,
            "seconds": round(voiced["seconds"] / tempo, 2),
        },
        "fps": FPS,
        "width": 1080,
        "height": 1920,
    }


def render(item_id: int, report: Optional[Callable[[str], None]] = None) -> dict:
    """Render one reel. Returns where it landed and how long it took."""
    say = report or (lambda _text: None)
    ok, note = ready()
    if not ok:
        raise RuntimeError(note)

    props = build_props(item_id)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{item_id}.mp4"
    props_file = OUT_DIR / f"{item_id}.props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    say(f"рендер · {len(props['beats'])} битов")
    started = time.time()
    result = subprocess.run(
        [str(BINARY), "render", "src/index.ts", "reel", str(out),
         f"--props={props_file}", "--log=error"],
        cwd=str(RENDER_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
    )
    if result.returncode != 0 or not out.exists():
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-6:]
        raise RuntimeError("Remotion не справился:\n" + "\n".join(tail))

    seconds = round(time.time() - started, 1)
    size = out.stat().st_size
    x(
        "INSERT INTO reels(feed_item_id, path, seconds, size_bytes, pack, created_at) "
        "VALUES(?,?,?,?,?,?) ON CONFLICT(feed_item_id) DO UPDATE SET "
        "path=excluded.path, seconds=excluded.seconds, size_bytes=excluded.size_bytes, "
        "pack=excluded.pack, created_at=excluded.created_at",
        item_id, str(out), props["audio"]["seconds"], size, props["pack"], now(),
    )
    log.info("ролик: %.1f сек видео, %.1f сек рендера, %s МБ",
             props["audio"]["seconds"], seconds, round(size / 1024 / 1024, 1))
    return {
        "path": str(out),
        "seconds": props["audio"]["seconds"],
        "render_seconds": seconds,
        "size": size,
    }


def read(item_id: int) -> Optional[dict]:
    row = q1("SELECT * FROM reels WHERE feed_item_id=?", item_id)
    if row is None:
        return None
    return {
        "path": row["path"],
        "seconds": row["seconds"],
        "size": row["size_bytes"],
        "pack": row["pack"],
    }
