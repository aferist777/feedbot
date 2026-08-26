"""Writing the reel script, as a job."""
import asyncio
import logging

from app.db.repo import owner_id
from app.jobs.worker import JobCtx, register
from app.reel import script

log = logging.getLogger("feedbot.jobs.script")


@register("script.run")
async def script_run(payload: dict, ctx: JobCtx) -> None:
    item_id = int(payload.get("item_id") or 0)
    made = await asyncio.to_thread(script.make, item_id, str(payload.get("mode") or "retell"))

    chat = ctx.chat_id or owner_id()
    if not chat:
        return
    lines = [f"<b>Сценарий</b> · {len(made['beats'])} битов · ~{made['seconds']:.0f} сек",
             f"<i>{made['hook']}</i>", ""]
    for index, beat in enumerate(made["beats"], 1):
        lines.append(f"{index}. <b>{beat['on_screen']}</b>\n{beat['vo']}")
    await ctx.bot.send_message(chat, "\n".join(lines)[:4000])
