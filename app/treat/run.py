"""Running one treatment over one post."""
import logging
from typing import Optional

from app.db.base import q1, x
from app.db.repo import now
from app.llm import client, models
from app.treat.registry import BY_ID, SCHEMA

log = logging.getLogger("feedbot.treat")


def _post(item_id: int) -> Optional[dict]:
    row = q1(
        "SELECT fi.id, fi.feed_id, ri.title, ri.body, ri.url, ri.score, ri.comments, "
        "s.name AS source, f.name AS feed, f.note AS niche "
        "FROM feed_items fi "
        "JOIN raw_items ri ON ri.id = fi.raw_item_id "
        "JOIN sources s ON s.id = ri.source_id "
        "JOIN feeds f ON f.id = fi.feed_id "
        "WHERE fi.id=?",
        item_id,
    )
    return dict(row) if row is not None else None


def treat(item_id: int, mode_id: str, model: str = "") -> dict:
    """Produce the write-up and keep it. Re-running replaces the previous one."""
    mode = BY_ID.get(mode_id)
    if mode is None:
        raise ValueError(f"нет такой обработки: {mode_id}")
    post = _post(item_id)
    if post is None:
        raise ValueError("нет такого поста")

    body = (post["body"] or "").strip()
    title = (post["title"] or "").strip()
    if len(body) + len(title) < 80:
        # Nothing to retell. Better said here than discovered as three empty
        # sentences the model invented to fill the space.
        raise ValueError("в посте почти нет текста — пересказывать нечего")

    messages = [
        {"role": "system", "content": mode.system(post["niche"] or post["feed"])},
        {"role": "user", "content":
            f"r/{post['source']} · {post['score']} голосов · "
            f"{post['comments']} комментариев\n\n"
            f"{title or '(заголовок снят модератором)'}\n\n{body[:6000]}"},
    ]
    chain = [model] if model else models.write_chain()
    # The token ceiling is generous because reasoning models spend most of it
    # before writing a word: 1200-2000 tokens of thinking on a short post.
    answer, used = models.try_models(chain, lambda name: client.ask(
        name, messages, schema=SCHEMA,
        max_tokens=models.max_tokens(), temperature=models.temperature(),
    ))

    made = {
        "title": str(answer.get("title") or "").strip(),
        "hook": str(answer.get("hook") or "").strip(),
        "text": str(answer.get("text") or "").strip(),
    }
    x(
        "INSERT INTO treatments(feed_item_id, mode, title, hook, text, model, created_at) "
        "VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(feed_item_id, mode) DO UPDATE SET "
        "title=excluded.title, hook=excluded.hook, text=excluded.text, "
        "model=excluded.model, created_at=excluded.created_at",
        item_id, mode_id, made["title"], made["hook"], made["text"], used, now(),
    )
    log.info("%s: %s знаков", mode_id, len(made["text"]))
    return made
