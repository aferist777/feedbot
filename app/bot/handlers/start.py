from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.handlers.panel import panel_button
from app.db.repo import active_feed, claim_owner, owner_id

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    if owner_id() is None:
        if claim_owner(user.id, user.username or ""):
            await message.answer(
                "Готово, теперь бот твой.\n\nВсё настраивается в админке — она откроется "
                "окном на этом же компьютере.",
                reply_markup=panel_button(),
            )
        return  # waiting for a specific username, and this is not it

    feed = active_feed()
    where = f"Активная лента: <b>{feed['name']}</b>" if feed else "Лент пока нет."
    await message.answer(f"feedbot на месте.\n{where}", reply_markup=panel_button())
