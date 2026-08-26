"""The three keys the app needs, and how to check each one is real.

A key is never sent to the window with the page — the window asks for one
explicitly, by id, and gets that one back. What it receives unasked is a mask:
the length and the last four characters, enough to tell two keys apart.

All three are stored under the "cfg:" prefix, which app.config reads once at
import. That is why the panel says "после перезапуска" next to them.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app import config
from app.db.repo import sdel, sget, sset

log = logging.getLogger("feedbot.panel.keys")

CFG = "cfg:"


@dataclass
class KeySpec:
    id: str
    label: str
    env: str
    hint: str
    required: bool


SPECS: list[KeySpec] = [
    KeySpec("tg", "Telegram", "TG_TOKEN",
            "от @BotFather", True),
    KeySpec("openrouter", "OpenRouter", "OPENROUTER_API_KEY",
            "всё, что генерируется, идёт через него", True),
    KeySpec("eleven", "ElevenLabs", "ELEVENLABS_API_KEY",
            "необязательно: без него озвучка идёт через Edge", False),
]

BY_ID = {spec.id: spec for spec in SPECS}


def value(key_id: str) -> str:
    """The live value: what the panel saved, else what .env brought in."""
    spec = BY_ID[key_id]
    return (sget(CFG + spec.env) or "").strip() or getattr(config, spec.env, "") or ""


def save(key_id: str, raw: str) -> None:
    sset(CFG + BY_ID[key_id].env, raw.strip())


def clear(key_id: str) -> None:
    sdel(CFG + BY_ID[key_id].env)


def mask(raw: str) -> Optional[str]:
    if not raw:
        return None
    tail = raw[-4:] if len(raw) > 8 else ""
    return "•" * min(len(raw), 20) + (f" {tail}" if tail else "")


async def check(key_id: str, raw: str) -> tuple[bool, str]:
    """Ask the service itself whether the key works.

    Checked before saving, so a typo never reaches the database and the app
    never starts up with a key that was wrong from the first minute.
    """
    raw = raw.strip()
    if not raw:
        return False, "пусто"
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            if key_id == "tg":
                r = await http.get(f"https://api.telegram.org/bot{raw}/getMe")
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                if r.status_code == 200 and data.get("ok"):
                    return True, "@" + (data["result"].get("username") or "бот")
                return False, (data.get("description") or f"HTTP {r.status_code}")[:120]

            if key_id == "openrouter":
                r = await http.get(
                    "https://openrouter.ai/api/v1/key",
                    headers={"Authorization": f"Bearer {raw}"},
                )
                if r.status_code == 200:
                    data = (r.json() or {}).get("data") or {}
                    limit = data.get("limit")
                    used = data.get("usage")
                    if limit is None:
                        return True, f"ключ живой, потрачено ${used or 0:.2f}"
                    return True, f"осталось ${max(float(limit) - float(used or 0), 0):.2f}"
                return False, f"HTTP {r.status_code}"

            if key_id == "eleven":
                r = await http.get(
                    "https://api.elevenlabs.io/v1/user", headers={"xi-api-key": raw}
                )
                if r.status_code == 200:
                    tier = ((r.json() or {}).get("subscription") or {}).get("tier")
                    return True, f"тариф {tier}" if tier else "ключ живой"
                return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"сеть молчит: {exc}"
    return False, "неизвестный ключ"


def payload() -> list[dict]:
    out = []
    for spec in SPECS:
        raw = value(spec.id)
        out.append({
            "id": spec.id,
            "label": spec.label,
            "env": spec.env,
            "hint": spec.hint,
            "required": spec.required,
            "mask": mask(raw),
            "filled": bool(raw),
        })
    return out
