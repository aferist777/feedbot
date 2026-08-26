"""How a reel looks. One set of knobs per feed.

Kept as a flat list with a kind and a hint per field, so the panel draws itself
from this and adding a knob is one entry here.
"""
import json
from typing import Any, Optional

from app.db.base import q1, x

FIELDS: list[dict[str, Any]] = [
    {"key": "bg", "label": "Фон", "kind": "color", "default": "#14161a",
     "hint": "основной цвет кадра"},
    {"key": "ink", "label": "Сказанное", "kind": "color", "default": "#e6e9ee",
     "hint": "слова, которые уже прозвучали"},
    {"key": "dim", "label": "Ещё не сказанное", "kind": "color", "default": "#3a3f48",
     "hint": "слова впереди — их видно, но приглушённо"},
    {"key": "accent", "label": "Акцент", "kind": "color", "default": "#d8a657",
     "hint": "слово, которое произносится прямо сейчас"},
    {"key": "font", "label": "Шрифт", "kind": "line", "default": "Segoe UI",
     "hint": "берётся из системы; шрифт должен быть установлен"},
    {"key": "fontSize", "label": "Размер текста", "kind": "int", "default": 84,
     "hint": "потолок: длинные биты уменьшаются сами"},
    {"key": "captionSize", "label": "Размер надписи", "kind": "int", "default": 44,
     "hint": "строка внизу, которую читают без звука"},
    {"key": "safeTop", "label": "Отступ сверху", "kind": "int", "default": 260,
     "hint": "место под интерфейс площадки"},
    {"key": "safeBottom", "label": "Отступ снизу", "kind": "int", "default": 340,
     "hint": "подпись и кнопки инстаграма перекрывают низ"},
    {"key": "showCaption", "label": "Показывать надпись", "kind": "bool", "default": True,
     "hint": "выключи, если субтитры делаешь в приложении"},
    {"key": "wordEnter", "label": "Появление слова, сек", "kind": "float", "default": 0.22,
     "hint": "меньше — резче, больше — мягче"},
    {"key": "background", "label": "Подложка", "kind": "select", "default": "gradient",
     "options": [["flat", "ровная"], ["gradient", "градиент"], ["vignette", "виньетка"]],
     "hint": "как окрашен фон за текстом"},
]

BY_KEY = {field["key"]: field for field in FIELDS}


def _cast(key: str, raw: Any) -> Any:
    kind = BY_KEY[key]["kind"]
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "bool":
        return bool(raw) if isinstance(raw, bool) else str(raw) not in ("0", "false", "")
    return str(raw).strip()


def read(feed_id: int) -> dict:
    """Defaults, with whatever this feed overrode on top."""
    row = q1("SELECT theme_json FROM feeds WHERE id=?", feed_id)
    saved: dict = {}
    if row is not None:
        try:
            saved = json.loads(row["theme_json"] or "{}")
        except json.JSONDecodeError:
            saved = {}
    theme = {field["key"]: field["default"] for field in FIELDS}
    for key, value in saved.items():
        if key in BY_KEY:
            try:
                theme[key] = _cast(key, value)
            except (TypeError, ValueError):
                pass
    return theme


def write(feed_id: int, key: str, raw: Any) -> dict:
    if key not in BY_KEY:
        raise KeyError(key)
    theme = read(feed_id)
    theme[key] = _cast(key, raw)
    # Only what differs from the default is stored, so changing a default later
    # moves every feed that never touched it.
    diff = {k: v for k, v in theme.items() if v != BY_KEY[k]["default"]}
    x("UPDATE feeds SET theme_json=? WHERE id=?",
      json.dumps(diff, ensure_ascii=False), feed_id)
    return theme


def reset(feed_id: int, key: Optional[str] = None) -> dict:
    if key is None:
        x("UPDATE feeds SET theme_json='{}' WHERE id=?", feed_id)
        return read(feed_id)
    theme = read(feed_id)
    theme.pop(key, None)
    diff = {k: v for k, v in theme.items()
            if k in BY_KEY and v != BY_KEY[k]["default"]}
    x("UPDATE feeds SET theme_json=? WHERE id=?",
      json.dumps(diff, ensure_ascii=False), feed_id)
    return read(feed_id)


def payload(feed_id: int) -> list[dict]:
    theme = read(feed_id)
    return [{**field, "value": theme[field["key"]]} for field in FIELDS]
