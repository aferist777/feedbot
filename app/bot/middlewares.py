"""The bot answers one person: whoever claimed it first.

Until an owner exists every update passes, so that the very first /start can
claim it. After that everyone else is silently ignored — no reply at all,
because an error message is itself a signal that the bot is here.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.db.repo import owner_id

log = logging.getLogger("feedbot.guard")


class OwnerOnly(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        owner = owner_id()
        user: User | None = data.get("event_from_user")
        if owner is None or user is None or user.id == owner:
            return await handler(event, data)
        log.info("ignored update from %s (@%s)", user.id, user.username)
        return None
