"""The voice-over, and the word timings the whole picture hangs off.

Edge TTS is free and needs no key. Two things about it are not obvious and
both are load-bearing here:

  * it reports sentence boundaries unless you ask for words explicitly, and
    word timings are the only reason this module exists;
  * its `rate` parameter barely moves Russian voices — measured from +0% to
    +25% the length changes by tenths of a second. So speed is not applied
    here at all: the raw audio is kept, and playback speeds it up while the
    timings are divided by the same number.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import edge_tts

from app.config import DATA_DIR
from app.db.base import q1, x
from app.db.repo import now

log = logging.getLogger("feedbot.reel.voice")

VOICE_DIR = DATA_DIR / "voice"

VOICES = [
    ("ru-RU-DmitryNeural", "Дмитрий"),
    ("ru-RU-SvetlanaNeural", "Светлана"),
]


ATTEMPTS = 3
PAUSE = 6.0


async def _once(text: str, voice: str, out: Path) -> list[dict]:
    speech = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words: list[dict] = []
    with out.open("wb") as sink:
        async for chunk in speech.stream():
            if chunk["type"] == "audio":
                sink.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # Edge counts in 100-nanosecond ticks.
                start = chunk["offset"] / 1e7
                words.append({
                    "text": chunk["text"],
                    "start": round(start, 3),
                    "end": round(start + chunk["duration"] / 1e7, 3),
                })
    return words


async def _synthesize(text: str, voice: str, out: Path) -> list[dict]:
    """Write the mp3 and collect one entry per spoken word.

    Edge refuses now and then with "No audio was received" — it is a free
    service and it throttles. One reel out of five died on it, so a refusal is
    waited out rather than passed up: the text is unchanged, only the timing
    of the request differs.
    """
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(PAUSE * attempt)
            log.warning("Edge отказал, попытка %s из %s", attempt + 1, ATTEMPTS)
        try:
            words = await _once(text, voice, out)
        except Exception as exc:  # edge-tts raises its own NoAudioReceived
            last = exc
            continue
        if words and out.stat().st_size > 1024:
            return words
        last = RuntimeError("Edge вернул пустую озвучку")
    raise RuntimeError(f"озвучка не удалась после {ATTEMPTS} попыток: {last}")


def speak(item_id: int, voice: str = "") -> dict:
    """Voice the script of one post. Re-running replaces what was there."""
    row = q1(
        "SELECT s.vo_text, f.voice FROM scripts s "
        "JOIN feed_items fi ON fi.id = s.feed_item_id "
        "JOIN feeds f ON f.id = fi.feed_id WHERE s.feed_item_id=?",
        item_id,
    )
    if row is None:
        raise ValueError("сначала нужен сценарий")
    text = (row["vo_text"] or "").strip()
    if not text:
        raise ValueError("в сценарии нет закадрового текста")

    used = voice or row["voice"] or VOICES[0][0]
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    out = VOICE_DIR / f"{item_id}.mp3"

    words = asyncio.run(_synthesize(text, used, out))
    if not words:
        raise ValueError("Edge не вернул ни одного слова — озвучка не удалась")
    seconds = words[-1]["end"]

    x(
        "INSERT INTO voiceovers(feed_item_id, path, seconds, words_json, voice, created_at) "
        "VALUES(?,?,?,?,?,?) ON CONFLICT(feed_item_id) DO UPDATE SET "
        "path=excluded.path, seconds=excluded.seconds, words_json=excluded.words_json, "
        "voice=excluded.voice, created_at=excluded.created_at",
        item_id, str(out), seconds, json.dumps(words, ensure_ascii=False), used, now(),
    )
    log.info("озвучка: %s слов, %.1f сек, %s КБ",
             len(words), seconds, out.stat().st_size // 1024)
    return {"words": words, "seconds": seconds, "path": str(out), "voice": used}


def read(item_id: int) -> Optional[dict]:
    row = q1("SELECT * FROM voiceovers WHERE feed_item_id=?", item_id)
    if row is None:
        return None
    try:
        words = json.loads(row["words_json"] or "[]")
    except json.JSONDecodeError:
        words = []
    return {
        "path": row["path"],
        "seconds": row["seconds"],
        "words": words,
        "voice": row["voice"],
    }


def _repunctuate(spoken: list[dict], vo: str) -> list[dict]:
    """Put the punctuation back.

    Edge reports what it says, not what it read: "вечер." comes back as
    "вечер". On screen that reads as one long breathless line, so each timing
    is matched back to its token in the original text — and only replaced when
    the two really are the same word, so a mismatch cannot shift the whole beat.
    """
    tokens = vo.split()
    out = []
    for index, word in enumerate(spoken):
        text = word["text"]
        if index < len(tokens):
            token = tokens[index]
            bare = token.strip(".,!?:;—–-«»\"'()[]")
            if bare.lower() == text.lower():
                text = token
        out.append({**word, "text": text})
    return out


def beat_words(item_id: int, beats: list[dict], tempo: float = 1.0) -> list[dict]:
    """Split the word timings between beats, at playback speed.

    The whole script is voiced in one go — voicing beat by beat leaves Edge's
    own pause at every seam, and the reel stumbles on each of them. So the cut
    points are found in the timings instead: a beat lives until the first word
    of the next one.
    """
    voice = read(item_id)
    if voice is None:
        return []
    words = voice["words"]
    tempo = max(tempo, 0.1)

    cursor = 0
    out: list[dict] = []
    for index, beat in enumerate(beats):
        spoken = len((beat.get("vo") or "").split())
        chunk = words[cursor : cursor + spoken]
        cursor += spoken
        if not chunk:
            continue
        start = chunk[0]["start"] / tempo
        # A beat ends where the next one starts, so nothing is left silent
        # between them; the last one ends with its own last word.
        following = words[cursor]["start"] if cursor < len(words) else chunk[-1]["end"]
        out.append({
            "index": index,
            "start": round(start, 3),
            "end": round(following / tempo, 3),
            "words": _repunctuate([
                {"text": word["text"],
                 "start": round(word["start"] / tempo, 3),
                 "end": round(word["end"] / tempo, 3)}
                for word in chunk
            ], beat.get("vo") or ""),
        })
    return out
