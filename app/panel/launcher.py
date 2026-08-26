"""Opening the panel window from inside the bot process.

Pressing the button twice must not give you two windows, so an existing one is
raised instead of a second being spawned.
"""
import ctypes
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.config import ROOT
from app.panel.window import TITLE

log = logging.getLogger("feedbot.panel.window")

CREATE_NO_WINDOW = 0x08000000
SW_RESTORE = 9

_proc: Optional[subprocess.Popen] = None


def _interpreter() -> str:
    """pythonw next to python, so the window does not drag a console along."""
    windowless = Path(sys.executable).with_name("pythonw.exe")
    return str(windowless) if windowless.exists() else sys.executable


def _raise_existing() -> bool:
    """Bring the already-open window to the front. Windows only, by design."""
    try:
        user32 = ctypes.windll.user32
    except AttributeError:
        return False  # not Windows: nothing to raise
    handle = user32.FindWindowW(None, TITLE)
    if not handle:
        return False
    user32.ShowWindow(handle, SW_RESTORE)
    user32.SetForegroundWindow(handle)
    return True


def is_open() -> bool:
    return _proc is not None and _proc.poll() is None


def open_window() -> str:
    """Returns what happened, so the bot can say it out loud."""
    global _proc
    if is_open():
        _raise_existing()
        return "уже открыта"
    _proc = subprocess.Popen(
        [_interpreter(), "-m", "app.panel.window"],
        cwd=str(ROOT),
        creationflags=CREATE_NO_WINDOW,
    )
    log.info("panel window started, pid %s", _proc.pid)
    return "открыл"


def close_window() -> None:
    global _proc
    if is_open() and _proc is not None:
        _proc.terminate()
    _proc = None
