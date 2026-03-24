"""
ConfigManager - application-wide settings (port, autostart, language, theme, etc.)
Stored in ~/.macro_deck/config.json
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("macro_deck.config")

_CONFIG_FILE = Path.home() / ".macro_deck" / "config.json"

_DEFAULTS = {
    "port": 8191,
    "host": "0.0.0.0",
    "autostart": False,
    "start_minimized": False,
    "language": "en",
    "theme": "dark",
    "log_level": "INFO",
    "show_notifications": True,
    "check_updates": True,
    "deck_rows": 4,
    "deck_cols": 8,
    "gui_enabled": True,
    "web_config_port": 8193,
}


class ConfigManager:
    _cfg: dict = {}
    _active_path: Path = _CONFIG_FILE

    @classmethod
    def load(cls, path: Optional[Path] = None) -> None:
        if path is not None:
            cls._active_path = path
        data = {}
        if cls._active_path.exists():
            try:
                with open(cls._active_path) as f:
                    data = json.load(f)
            except Exception as exc:
                logger.error("Config load error: %s", exc)
        cls._cfg = {**_DEFAULTS, **data}

    @classmethod
    def save(cls, path: Optional[Path] = None) -> None:
        target = path if path is not None else cls._active_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            json.dump(cls._cfg, f, indent=2)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        return cls._cfg.get(key, default)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        cls._cfg[key] = value
        cls.save()

    @classmethod
    def as_dict(cls) -> dict:
        return dict(cls._cfg)
