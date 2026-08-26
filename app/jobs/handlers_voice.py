"""Voicing a script, as a job."""
import asyncio
import logging

from aiogram.types import FSInputFile

from app.db.repo import owner_id
from app.jobs.worker import JobCtx, register
from app.reel import voice

log = logging.getLogger("feedbot.jobs.voice")


@register("voice.run")
async def voice_run(payload: dict, ctx: JobCtx) -> None:
    item_id = int(payload.get("item_id") or 0)
    made = await asyncio.to_thread(voice.speak, item_id, str(payload.get("voice") or ""))

    chat = ctx.chat_id or owner_id()
    if not chat:
        return
    await ctx.bot.send_audio(
        chat,
        FSInputFile(made["path"]),
        caption=f"Озвучка · {len(made['words'])} слов · {made['seconds']:.0f} сек · {made['voice']}",
    )
