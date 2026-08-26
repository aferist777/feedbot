"""Turning a taken post into something of our own."""
import asyncio
import logging

from app.db.base import q1
from app.db.repo import owner_id
from app.jobs.worker import JobCtx, register
from app.treat import run
from app.treat.registry import BY_ID

log = logging.getLogger("feedbot.jobs.treat")


@register("treat.run")
async def treat_run(payload: dict, ctx: JobCtx) -> None:
    item_id = int(payload.get("item_id") or 0)
    mode_id = str(payload.get("mode") or "retell")
    mode = BY_ID.get(mode_id)
    if mode is None:
        raise ValueError(f"нет обработки {mode_id}")

    made = await asyncio.to_thread(run.treat, item_id, mode_id)

    row = q1(
        "SELECT ri.url FROM feed_items fi JOIN raw_items ri ON ri.id = fi.raw_item_id "
        "WHERE fi.id=?", item_id,
    )
    chat = ctx.chat_id or owner_id()
    if not chat:
        return
    # Telegram cuts a message at 4096; a retelling is a fifth of that, but a
    # future treatment might not be.
    body = made["text"]
    text = (
        f"<b>{made['title']}</b>\n<i>{made['hook']}</i>\n\n{body}"
        f"\n\n<a href=\"{row['url'] if row else ''}\">оригинал</a>"
    )[:4000]
    await ctx.bot.send_message(chat, text, disable_web_page_preview=True)
