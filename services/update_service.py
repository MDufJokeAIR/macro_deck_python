"""
UpdateService - mirrors SuchByte.MacroDeck.UpdateService
Polls GitHub releases for a newer version and pushes a notification via WebSocket.
"""
from __future__ import annotations
import json
import logging
import threading
import urllib.request
from typing import Callable, Optional, Tuple

logger = logging.getLogger("macro_deck.update")

APP_VERSION = "2.14.1"
RELEASES_API = "https://api.github.com/repos/Macro-Deck-App/Macro-Deck/releases/latest"
CHECK_INTERVAL_S = 3600   # check every hour


def _parse_version(ver: str) -> Tuple[int, ...]:
    """'2.14.1' → (2, 14, 1)"""
    try:
        cleaned = ver.lstrip("v").strip()
        return tuple(int(x) for x in cleaned.split("."))
    except ValueError:
        return (0,)


def _is_newer(remote: str, current: str = APP_VERSION) -> bool:
    return _parse_version(remote) > _parse_version(current)


class UpdateService:
    _timer: Optional[threading.Timer] = None
    _on_update_available: Optional[Callable[[str, str], None]] = None  # (version, url)

    @classmethod
    def start(cls, on_update_available: Optional[Callable[[str, str], None]] = None) -> None:
        cls._on_update_available = on_update_available
        cls._schedule()

    @classmethod
    def stop(cls) -> None:
        if cls._timer:
            cls._timer.cancel()
            cls._timer = None

    @classmethod
    def check_now(cls) -> Optional[Tuple[str, str]]:
        try:
            req = urllib.request.Request(
                RELEASES_API,
                headers={"User-Agent": f"MacroDeck-Python/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            tag = data.get("tag_name", "")
            url = data.get("html_url", "")
            if tag and _is_newer(tag):
                logger.info("Update available: %s", tag)
                if cls._on_update_available:
                    cls._on_update_available(tag, url)
                return tag, url
        except Exception as exc:
            logger.debug("Update check failed: %s", exc)
        return None

    @classmethod
    def _schedule(cls) -> None:
        cls._timer = threading.Timer(CHECK_INTERVAL_S, cls._run)
        cls._timer.daemon = True
        cls._timer.start()
        # Also check immediately in background
        t = threading.Thread(target=cls.check_now, daemon=True)
        t.start()

    @classmethod
    def _run(cls) -> None:
        cls.check_now()
        cls._schedule()
