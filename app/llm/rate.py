"""The third signal: how interesting a post is, which no counter can tell you.

Score and comments say a post did well on Reddit. They cannot say whether it
would carry a ninety-second video, and that is what the feed is for.
"""
import logging
from typing import Callable, Optional

from app.db.base import q, x
from app.db.repo import now
from app.llm import client, models

log = logging.getLogger("feedbot.rate")

SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "interesting": {"type": "integer"},
                    "why": {"type": "string"},
                },
                "required": ["id", "interesting", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["posts"],
    "additionalProperties": False,
}

PROMPT = """Ты отбираешь посты для коротких вертикальных роликов.

Ниша: {niche}

Для каждого поста поставь interesting от 1 до 10 — насколько он потянет ролик
на полторы минуты. Высоко: конкретная история, необычный опыт, спор, цифры,
понятная развязка. Низко: вопрос без ответа, просьба посоветовать товар,
обсуждение, которое непонятно без контекста подписки, реклама.

why — одна короткая фраза по-русски, почему такая оценка.
Отвечай на все посты, ничего не пропускай."""


def _batch(niche: str, rows: list) -> dict[int, tuple[int, str]]:
    listing = [
        {
            "id": row["id"],
            # A stripped title is stored empty; the model gets the body either
            # way, so there is nothing to reconstruct for it.
            "title": row["title"] or "(заголовок снят модератором)",
            "text": (row["body"] or "")[:600],
            "score": row["score"],
            "comments": row["comments"],
        }
        for row in rows
    ]
    answer = client.ask(
        models.rate_model(),
        [
            {"role": "system", "content": PROMPT.format(niche=niche or "не задана")},
            {"role": "user", "content": str(listing)},
        ],
        schema=SCHEMA,
        max_tokens=models.max_tokens(),
    )
    out: dict[int, tuple[int, str]] = {}
    for item in answer.get("posts") or []:
        try:
            grade = max(1, min(10, int(item["interesting"])))
        except (KeyError, TypeError, ValueError):
            continue
        out[int(item["id"])] = (grade, str(item.get("why") or "")[:200])
    return out


def rate_feed(
    feed_id: int, niche: str, report: Optional[Callable[[str], None]] = None
) -> int:
    """Grade the most promising unrated items. Returns how many were graded.

    Only the top of the pile goes to the model: the rest already have a place
    from their counters, and a free tier is a budget like any other.
    """
    say = report or (lambda _text: None)
    rows = q(
        "SELECT fi.id, ri.title, ri.body, ri.score, ri.comments FROM feed_items fi "
        "JOIN raw_items ri ON ri.id = fi.raw_item_id "
        "WHERE fi.feed_id=? AND fi.state='new' AND fi.interesting IS NULL "
        "ORDER BY fi.rank DESC LIMIT ?",
        feed_id, models.rate_top(),
    )
    if not rows:
        return 0

    done = 0
    batch = models.rate_batch()
    for start in range(0, len(rows), batch):
        chunk = rows[start : start + batch]
        say(f"оцениваю {start + len(chunk)}/{len(rows)}")
        try:
            grades = _batch(niche, chunk)
        except client.LLMError as exc:
            # A batch that will not come back must not take the sweep with it;
            # what is already graded stays graded.
            log.warning("пачка не оценилась: %s", exc)
            break
        for row in chunk:
            grade = grades.get(row["id"])
            if grade is None:
                continue
            interesting, why = grade
            x(
                "UPDATE feed_items SET interesting=?, why=?, rated_at=?, "
                "rank=ROUND((COALESCE(hot,0)*0.4 + COALESCE(talk,0)*0.3 + ?*0.3)*100, 1) "
                "WHERE id=?",
                interesting, why, now(), interesting / 10.0, row["id"],
            )
            done += 1
    return done
