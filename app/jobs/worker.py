"""The loop that runs queued jobs.

A handler is registered by kind and receives the payload plus a context that
knows where the request came from, so it can report back into the same chat.
"""
import asyncio
import logging
import traceback
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from aiogram import Bot

from app.jobs import queue

log = logging.getLogger("feedbot.worker")

POLL_INTERVAL = 1.0

# Kinds a second, light lane would take. Empty until there are jobs short
# enough to be worth overtaking a long one; run_worker already supports it.
FAST_KINDS: set[str] = set()


@dataclass
class JobCtx:
    bot: Bot
    job_id: int
    kind: str
    chat_id: Optional[int]
    message_id: Optional[int]


JobHandler = Callable[[dict, JobCtx], Awaitable[None]]
_registry: dict[str, JobHandler] = {}


def register(kind: str) -> Callable[[JobHandler], JobHandler]:
    def deco(fn: JobHandler) -> JobHandler:
        _registry[kind] = fn
        return fn

    return deco


def known_kinds() -> list[str]:
    return sorted(_registry)


async def run_worker(bot: Bot, lane: str = "main") -> None:
    kinds = FAST_KINDS if lane == "fast" else None
    exclude = None if lane == "fast" else FAST_KINDS
    log.info("worker[%s] started", lane)
    while True:
        try:
            row = queue.claim(kinds=kinds, exclude=exclude)
        except Exception:
            log.exception("claim failed")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if row is None:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        handler = _registry.get(row["kind"])
        if handler is None:
            queue.fail(row["id"], 99, f"no handler for kind={row['kind']}")
            continue

        ctx = JobCtx(bot, row["id"], row["kind"], row["chat_id"], row["message_id"])
        try:
            await handler(queue.payload_of(row), ctx)
            queue.finish(row["id"])
        except Exception as exc:  # one bad job must never take the worker down
            log.error("job %s (%s) failed: %s", row["id"], row["kind"], exc)
            log.debug(traceback.format_exc())
            queue.fail(row["id"], row["attempts"], str(exc))
