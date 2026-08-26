"""Process entry point: the panel, one bot, one worker, one database.

Order matters here. The panel comes up first and unconditionally, because on a
first run it is the only thing that can supply the token the bot needs — the
app has to be able to configure itself.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app import config, log as applog
from app.bot.handlers import panel as panel_handlers, start
from app.bot.middlewares import OwnerOnly
from app.db.base import init_db
from app.jobs import queue
from app.jobs import (  # noqa: F401  — importing registers the job kinds
    handlers_collect, handlers_render, handlers_script, handlers_treat,
    handlers_voice,
)
from app.jobs.worker import run_worker
from app.panel import keys, launcher
from app.panel import server as panel

log = logging.getLogger("feedbot")

TOKEN_POLL = 2.0


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(panel_handlers.router)
    # Middlewares hang off each observer, not off the Dispatcher as a whole.
    dp.message.middleware(OwnerOnly())
    dp.callback_query.middleware(OwnerOnly())
    return dp


async def wait_for_token() -> str:
    """Block until the panel supplies a Telegram token.

    A fresh install has no token and therefore no bot, so the button that
    normally opens the panel cannot be pressed. The window opens by itself
    instead, and this loop watches the database for what it saves.
    """
    log.warning("no Telegram token — opening the panel window to ask for one")
    launcher.open_window()
    while True:
        token = keys.value("tg")
        if token:
            log.info("token arrived from the panel")
            return token
        await asyncio.sleep(TOKEN_POLL)


async def main() -> None:
    applog.setup()
    init_db()

    reclaimed = queue.reclaim_orphans()
    if reclaimed:
        log.info("requeued %s job(s) left running by a previous process", reclaimed)

    await panel.start()

    token = config.TG_TOKEN or await wait_for_token()

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    me = await bot.get_me()
    log.info("bot @%s is up", me.username)
    panel.set_bot(me.username or "bot")
    await bot.set_my_commands([
        BotCommand(command="start", description="что происходит"),
        BotCommand(command="admin", description="открыть админку"),
    ])

    worker = asyncio.create_task(run_worker(bot))
    try:
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        launcher.close_window()
        await panel.stop()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
