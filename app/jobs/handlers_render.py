"""Rendering the reel, as a job."""
import asyncio
import logging

from aiogram.types import FSInputFile

from app.db.repo import owner_id
from app.jobs import progress
from app.jobs.worker import JobCtx, register
from app.reel import render

log = logging.getLogger("feedbot.jobs.render")

# Telegram refuses anything larger from a bot.
TG_LIMIT = 48 * 1024 * 1024


@register("render.run")
async def render_run(payload: dict, ctx: JobCtx) -> None:
    item_id = int(payload.get("item_id") or 0)
    progress.start(item_id, "рендер")
    try:
        made = await asyncio.to_thread(
            render.render, item_id, lambda text: progress.set_text(item_id, text)
        )
    finally:
        progress.clear(item_id)

    chat = ctx.chat_id or owner_id()
    if not chat:
        return
    caption = (f"Ролик · {made['seconds']:.0f} сек · "
               f"{made['size'] / 1024 / 1024:.1f} МБ · "
               f"рендер {made['render_seconds']:.0f} сек")
    if made["size"] <= TG_LIMIT:
        await ctx.bot.send_video(chat, FSInputFile(made["path"]), caption=caption)
    else:
        await ctx.bot.send_message(chat, caption + f"\nСлишком велик для Telegram: {made['path']}")
