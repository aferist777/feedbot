"""The scene and icon catalogue, read from the same file the renderer reads.

One file, three readers: the prompt lists it so the model picks from a closed
set, this module falls back on its synonyms when the model picks badly, and
Remotion draws what it names. Keeping it in one place is what stops the three
from drifting apart.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import ROOT

CATALOG = ROOT / "render" / "catalog.json"

# Scenes that need items to make sense at all; without them the pack would
# draw an empty box, so they fall back to a plain line.
NEEDS_ITEMS = {"flow", "stack", "compare", "log"}


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def scenes() -> dict:
    return load()["scenes"]


def icons() -> dict:
    return load()["icons"]


def scene_list() -> str:
    """The scene menu, as the prompt shows it."""
    return "\n".join(
        f"  {name} — {spec['about']}; items: {spec['items']}"
        for name, spec in scenes().items()
    )


def icon_list() -> str:
    """Icon names only. The synonyms are ours, not the model's business."""
    names = list(icons())
    lines = []
    for start in range(0, len(names), 8):
        lines.append("  " + ", ".join(names[start : start + 8]))
    return "\n".join(lines)


def _words(text: str) -> list[str]:
    return re.findall(r"[\wа-яё-]+", (text or "").lower())


@lru_cache(maxsize=1)
def _stems() -> list[tuple[str, str]]:
    """Every synonym reduced to a stem, longest first.

    Stems rather than whole words because Russian declines everything —
    «сервера», «серверу» and «сервером» are all «сервер». Longest first so a
    word matches the most specific synonym that fits it.
    """
    pairs = []
    for name, synonyms in icons().items():
        for synonym in synonyms:
            stem = synonym[:-1] if len(synonym) > 5 else synonym
            pairs.append((stem, name))
    return sorted(pairs, key=lambda pair: -len(pair[0]))


def guess_icon(*texts: str) -> Optional[str]:
    """The safety net: find an icon by what the beat actually says.

    Two rules learned from getting it wrong: match the *start* of a word, never
    the middle — otherwise «просто» contains «рост» and every sentence is about
    growth. And take the earliest match in the sentence rather than the longest
    synonym: the first thing named is what the beat is about, so «письма в
    спам» is mail, not calendar because of the «неделю» at the end.
    """
    for word in _words(" ".join(texts)):
        for stem, name in _stems():
            if word.startswith(stem):
                return name
    return None


def fix(beat: dict) -> dict:
    """Make one beat's visual fields safe to render.

    The model is asked for a scene and an icon; this decides what happens when
    it names something that does not exist, or picks a scene it gave no items
    for. Nothing here invents content — it only downgrades to something that
    can actually be drawn.
    """
    scene = str(beat.get("scene") or "").strip().lower()
    if scene not in scenes():
        scene = "line"

    items = [str(item).strip() for item in (beat.get("items") or []) if str(item).strip()]
    items = items[:5]
    if scene in NEEDS_ITEMS and len(items) < 2:
        scene = "line"
    if scene == "compare" and len(items) != 2:
        scene = "line"

    icon = str(beat.get("icon") or "").strip().lower()
    if icon not in icons():
        icon = guess_icon(beat.get("vo", ""), beat.get("on_screen", ""),
                          " ".join(beat.get("keys") or [])) or ""

    return {**beat, "scene": scene, "items": items, "icon": icon}
