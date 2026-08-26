"""Logging for a bot that runs unattended for days: console to watch it live,
a file to read after the fact."""
import logging
import sys

from app.config import LOG_PATH

FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
DATEFMT = "%H:%M:%S"


def setup(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:  # setup() called twice — the panel process imports this too
        return
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(FORMAT, DATEFMT))
    root.addHandler(console)

    to_file = logging.FileHandler(LOG_PATH, encoding="utf-8")
    to_file.setFormatter(logging.Formatter(FORMAT, DATEFMT))
    root.addHandler(to_file)

    # aiogram narrates every update at INFO; that buries our own lines.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
