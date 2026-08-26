"""The sweep, as a job: fetch, place by the numbers, then ask the model.

Every slow step goes through to_thread. The bot shares this event loop, and a
sweep is minutes long — blocking it would make the bot look dead.
"""
import asyncio
import logging

from app.collect import collector
from app.db.base import q1
from app.db.repo import owner_id
from app.jobs import progress
from app.jobs.worker import JobCtx, register
from app.llm import rate
from app.llm.client import LLMError

log = logging.getLogger("feedbot.jobs.collect")


@register("collect.run")
async def collect_run(payload: dict, ctx: JobCtx) -> None:
    feed_id = int(payload.get("feed_id") or 0)
    feed = q1("SELECT * FROM feeds WHERE id=?", feed_id)
    if feed is None:
        raise ValueError(f"нет ленты {feed_id}")

    progress.start(feed_id, "собираю")
    try:
        report = lambda text: progress.set_text(feed_id, text)  # noqa: E731
        got = await asyncio.to_thread(collector.sweep, feed_id, report)

        progress.set_text(feed_id, "раскладываю по местам")
        placed = await asyncio.to_thread(collector.rank_unrated, feed_id)

        graded = 0
        note = ""
        try:
            graded = await asyncio.to_thread(
                rate.rate_feed, feed_id, feed["note"] or feed["name"], report
            )
        except LLMError as exc:
            # No key, or the free tier said no. The sweep still counts: the
            # posts are in and ranked by their counters.
            note = f"\nОценка моделью не прошла: {exc}"
            log.warning("rating skipped: %s", exc)
    finally:
        progress.clear(feed_id)

    text = (
        f"<b>{feed['name']}</b>\n"
        f"Источников: {got['sources']} · собрано {got['fetched']} · "
        f"новых для ленты {got['fresh']}\n"
        f"Разложено: {placed} · оценено моделью: {graded}{note}"
    )
    chat = ctx.chat_id or owner_id()
    if chat:
        await ctx.bot.send_message(chat, text)
