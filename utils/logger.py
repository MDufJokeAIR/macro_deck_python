"""
MacroDeckLogger - mirrors SuchByte.MacroDeck.Logging.MacroDeckLogger
Four log levels: Trace(1), Info(2), Warning(3), Error(4)
Writes to ~/.macro_deck/logs/macro_deck_<date>.log and to console.
"""
from __future__ import annotations
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from macro_deck_python.plugins.base import IMacroDeckPlugin

_LOG_DIR = Path.home() / ".macro_deck" / "logs"

# ── bootstrap Python's logging ────────────────────────────────────────
def _setup_logging(log_level: int = logging.DEBUG) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / f"macro_deck_{datetime.now():%Y-%m-%d}.log"

    fmt = "%(asctime)s [%(levelname)-8s] %(name)s - %(message)s"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(level=log_level, format=fmt, handlers=handlers, force=True)

_setup_logging()


class MacroDeckLogger:
    """Static façade matching the original C# API."""

    # loglevel 1
    @staticmethod
    def trace(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
        name = f"plugin.{plugin.package_id}" if plugin else "macro_deck"
        logging.getLogger(name).debug("[TRACE] %s", message)

    # loglevel 2
    @staticmethod
    def info(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
        name = f"plugin.{plugin.package_id}" if plugin else "macro_deck"
        logging.getLogger(name).info(message)

    # loglevel 3
    @staticmethod
    def warning(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
        name = f"plugin.{plugin.package_id}" if plugin else "macro_deck"
        logging.getLogger(name).warning(message)

    # loglevel 4
    @staticmethod
    def error(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
        name = f"plugin.{plugin.package_id}" if plugin else "macro_deck"
        logging.getLogger(name).error(message)
