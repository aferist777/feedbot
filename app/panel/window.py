"""The panel's window, as its own process.

pywebview insists on owning the main thread, and the main thread here belongs
to the asyncio loop that runs the bot. Rather than fight that, the window is a
child process: it can be closed, or crash, and the bot never notices.

Run as: python -m app.panel.window
"""
import webview

from app import config

TITLE = "feedbot"  # the launcher finds an already-open window by this exact title


def main() -> None:
    webview.create_window(
        TITLE,
        config.PANEL_URL,
        width=1120,
        height=780,
        min_size=(900, 620),
        background_color="#14161a",
    )
    webview.start()


if __name__ == "__main__":
    main()
