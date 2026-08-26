"""Values read once, at import.

Two sources, in this order: what the panel saved into the database, then the
.env file. The panel wins — that is what lets a person set the whole app up
from the window without ever opening a text editor. The cost is that these
values only change on restart, which is why the panel labels them so.
"""
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "feedbot.db"
LOG_PATH = DATA_DIR / "feedbot.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# The panel stores restart-level values under this prefix. Read with a bare
# sqlite3 connection rather than app.db.base, because that module imports this
# one — the dependency only points one way.
CFG = "cfg:"


def _stored(name: str) -> str:
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return ""  # first run: the database file does not exist yet
    try:
        row = con.execute("SELECT value FROM settings WHERE key=?", (CFG + name,)).fetchone()
        return (row[0] or "").strip() if row else ""
    except sqlite3.Error:
        return ""  # the file exists but has no schema yet
    finally:
        con.close()


def _env(name: str, default: str = "") -> str:
    return _stored(name) or (os.getenv(name) or default).strip()


TG_TOKEN = _env("TG_TOKEN")

# One provider, on purpose. Everything the app generates goes through
# OpenRouter; there is no second backend to keep in sync.
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")

# Optional: the voice layer falls back to Edge TTS, which needs no key.
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")

# Which model grades posts. The free tier of this one supports strict JSON
# schemas, which most :free models do not — checked against the live registry.
MODEL_RATE = _env("MODEL_RATE", "nvidia/nemotron-3-super-120b-a12b:free")
# How many of the best-by-counters posts are worth a model call, and how many
# go in one request. Both are budget knobs, not quality ones.
RATE_TOP = int(_env("RATE_TOP", "40"))
RATE_BATCH = int(_env("RATE_BATCH", "10"))

# Which model writes. Prose is a matter of taste, so this is meant to be changed.
MODEL_WRITE = _env("MODEL_WRITE", "nvidia/nemotron-3-ultra-550b-a55b:free")

# The panel is a window on this machine and nothing else may reach it.
PANEL_HOST = "127.0.0.1"
PANEL_PORT = int(_env("PANEL_PORT", "8770"))
PANEL_URL = f"http://{PANEL_HOST}:{PANEL_PORT}"
