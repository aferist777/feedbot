"""Turning a write-up into beats.

A beat is the unit everything downstream counts in: the voice reads one, the
frame illustrates one, the edit cuts between them. Written from a treatment
rather than from the raw post — the retelling has already decided what the
story is, and asking twice gives two different stories.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from app.db.base import q1, x
from app.reel import catalog
from app.db.repo import now
from app.llm import client, models

log = logging.getLogger("feedbot.reel.script")

PROMPT = Path(__file__).parent / "prompts" / "script.md"

# Measured on Edge TTS, ru-RU-DmitryNeural, raw output: 1079 characters came
# out as 88.5 seconds. That is 12.2 characters a second — the familiar figure
# of 15 belongs to sped-up playback, and using it on raw speech overshoots the
# target by a quarter.
CHARS_PER_SECOND = 12.2

SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "vo": {"type": "string"},
                    "on_screen": {"type": "string"},
                    "keys": {"type": "array", "items": {"type": "string"}},
                    "scene": {"type": "string"},
                    "icon": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["vo", "on_screen", "keys", "scene", "icon", "items"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["hook", "beats"],
    "additionalProperties": False,
}


def _shape(seconds: int, tempo: float = 1.0) -> dict:
    """How many beats a reel of this length wants, and how much text fits.

    Tempo belongs in the budget: the reel is measured after speeding up, so a
    ninety-second reel at 1.15 holds fifteen percent more words than one at 1.0.
    Roughly one beat per seven seconds: shorter and the voice cannot finish a
    thought, longer and the picture goes static.
    """
    chars = round(seconds * CHARS_PER_SECOND * max(tempo, 0.1))
    return {
        "seconds": seconds,
        "chars": chars,
        "min_beats": max(4, round(seconds / 9)),
        "max_beats": max(6, round(seconds / 5)),
    }


def _keys_in_vo(beat: dict) -> list[str]:
    """Keep only the key phrases that really occur in the voice-over.

    They exist to be found in the word timings later; one that does not appear
    verbatim would simply never fire, so it is dropped here rather than
    debugged there.
    """
    vo = (beat.get("vo") or "").lower()
    return [
        key for key in (beat.get("keys") or [])
        if isinstance(key, str) and key.strip() and key.strip().lower() in vo
    ]


def make(item_id: int, mode: str = "retell", model: str = "") -> dict:
    """Write the script for one post. Re-running replaces the previous one."""
    row = q1(
        "SELECT t.title, t.hook, t.text, f.name AS feed, f.note AS niche, "
        "f.reel_seconds, f.voice_tempo FROM treatments t "
        "JOIN feed_items fi ON fi.id = t.feed_item_id "
        "JOIN feeds f ON f.id = fi.feed_id "
        "WHERE t.feed_item_id=? AND t.mode=?",
        item_id, mode,
    )
    if row is None:
        raise ValueError("сначала нужен пересказ — сценарий пишется из него")

    shape = _shape(row["reel_seconds"], row["voice_tempo"])
    messages = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8").format(
            niche=row["niche"] or row["feed"],
            scenes=catalog.scene_list(), icons=catalog.icon_list(), **shape)},
        {"role": "user", "content": f"{row['title']}\n{row['hook']}\n\n{row['text']}"},
    ]
    chain = [model] if model else models.write_chain()
    answer, used = models.try_models(chain, lambda name: client.ask(
        name, messages, schema=SCHEMA,
        max_tokens=models.max_tokens(), temperature=models.temperature(),
    ))

    beats = []
    for raw in answer.get("beats") or []:
        vo = str(raw.get("vo") or "").strip()
        if not vo:
            continue
        # catalog.fix downgrades anything unrenderable rather than dropping the
        # beat: a made-up scene name becomes a plain line, a missing icon is
        # guessed from what the beat says.
        beats.append(catalog.fix({
            "vo": vo,
            "on_screen": str(raw.get("on_screen") or "").strip()[:60],
            "keys": _keys_in_vo(raw),
            "scene": raw.get("scene"),
            "icon": raw.get("icon"),
            "items": raw.get("items"),
            "seconds": round(len(vo) / CHARS_PER_SECOND
                             / max(row["voice_tempo"], 0.1), 1),
        }))
    if not beats:
        raise ValueError("модель не вернула ни одного бита")

    vo_text = " ".join(beat["vo"] for beat in beats)
    # Estimated at playback speed, so it can be compared with reel_seconds.
    seconds = round(len(vo_text) / CHARS_PER_SECOND / max(row["voice_tempo"], 0.1), 1)
    x(
        "INSERT INTO scripts(feed_item_id, source_mode, hook, beats_json, vo_text, "
        "seconds_est, model, created_at) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(feed_item_id) DO UPDATE SET source_mode=excluded.source_mode, "
        "hook=excluded.hook, beats_json=excluded.beats_json, vo_text=excluded.vo_text, "
        "seconds_est=excluded.seconds_est, model=excluded.model, "
        "created_at=excluded.created_at",
        item_id, mode, str(answer.get("hook") or "").strip(),
        json.dumps(beats, ensure_ascii=False), vo_text, seconds, used, now(),
    )
    log.info("сценарий: %s битов, %.0f секунд (цель %s)",
             len(beats), seconds, row["reel_seconds"])
    return {"hook": answer.get("hook"), "beats": beats, "seconds": seconds}


def read(item_id: int) -> Optional[dict]:
    row = q1("SELECT * FROM scripts WHERE feed_item_id=?", item_id)
    if row is None:
        return None
    try:
        beats = json.loads(row["beats_json"] or "[]")
    except json.JSONDecodeError:
        beats = []
    return {
        "hook": row["hook"],
        "beats": beats,
        "seconds": row["seconds_est"],
        "model": row["model"],
        "mode": row["source_mode"],
    }
