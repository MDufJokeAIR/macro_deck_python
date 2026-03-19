"""
System tray icon - mirrors the WinForms tray icon in Macro Deck.
Uses pystray + PIL. Falls back gracefully if not available.
"""
from __future__ import annotations
import logging
import threading
import webbrowser
from typing import Callable, Optional

logger = logging.getLogger("macro_deck.tray")


def _make_icon():
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Simple grid icon
        d.rectangle([4, 4, 28, 28], fill="#7c83fd")
        d.rectangle([36, 4, 60, 28], fill="#7c83fd")
        d.rectangle([4, 36, 28, 60], fill="#7c83fd")
        d.rectangle([36, 36, 60, 60], fill="#5a62e0")
        return img
    except ImportError:
        return None


class TrayIcon:
    def __init__(
        self,
        web_config_port: int = 8193,
        on_quit: Optional[Callable[[], None]] = None,
    ):
        self.web_config_port = web_config_port
        self.on_quit = on_quit
        self._icon = None

    def start(self) -> None:
        try:
            import pystray
        except ImportError:
            logger.info("pystray not installed; tray icon disabled")
            return

        img = _make_icon()
        if img is None:
            logger.info("PIL not installed; tray icon disabled")
            return

        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("Open Config UI", self._open_config),
            pystray.MenuItem("Quit Macro Deck", self._quit),
        )
        self._icon = pystray.Icon("Macro Deck", img, "Macro Deck", menu)

        t = threading.Thread(target=self._icon.run, daemon=True)
        t.start()
        logger.info("Tray icon started")

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _open_config(self, icon, item) -> None:
        webbrowser.open(f"http://localhost:{self.web_config_port}")

    def _quit(self, icon, item) -> None:
        self.stop()
        if self.on_quit:
            self.on_quit()
