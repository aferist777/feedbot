"""Opening the panel from the chat.

The window lives on the same machine as the bot, so "open the panel" is a
local action triggered remotely: the button says what happened, and nothing is
sent back except that word.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.panel import launcher

router = Router()


def panel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎛 Админка", callback_data="panel:open")]
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer("Панель:", reply_markup=panel_button())


@router.callback_query(F.data == "panel:open")
async def open_panel(call: CallbackQuery) -> None:
    try:
        what = launcher.open_window()
    except OSError as exc:
        await call.answer(f"не смог открыть: {exc}", show_alert=True)
        return
    await call.answer(f"Админка: {what} на компьютере")
