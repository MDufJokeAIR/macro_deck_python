"""
Built-in plugin: keyboard actions.
Uses the native injector backend (Windows SendInput / macOS Quartz / xdotool / evdev)
instead of pyautogui — no extra dependency needed.
"""
from __future__ import annotations
import ast
import json
import logging
import time
from typing import List, TYPE_CHECKING

from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction
from macro_deck_python.plugins.builtin.keyboard_macro import injector

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton

logger = logging.getLogger("plugin.keyboard")


def _parse_config(configuration: str) -> dict:
    """Parse configuration string that may be JSON or Python-repr (single quotes)."""
    if not configuration:
        return {}
    # Try standard JSON first
    try:
        return json.loads(configuration)
    except json.JSONDecodeError:
        pass
    # Fall back to Python literal (handles single-quoted dicts from the editor)
    try:
        result = ast.literal_eval(configuration)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    logger.warning("Could not parse configuration: %r", configuration)
    return {}


class HotkeyAction(PluginAction):
    action_id = "hotkey"
    name = "Press Hotkey"
    description = "Simulate a keyboard hotkey (e.g. ctrl+c)"
    can_configure = True

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        try:
            cfg = _parse_config(self.configuration)
            keys = cfg.get("keys", "")
            if keys:
                parts = [k.strip().lower() for k in keys.split("+")]
                injector.combo(parts)
        except Exception as exc:
            logger.error("HotkeyAction error: %s", exc)


class TypeTextAction(PluginAction):
    action_id = "type_text"
    name = "Type Text"
    description = "Type a string of text"
    can_configure = True

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        try:
            cfg = _parse_config(self.configuration)
            text = cfg.get("text", "")
            interval = float(cfg.get("interval", 0.03))
            for ch in text:
                injector.press(ch)
                if interval > 0:
                    time.sleep(interval)
        except Exception as exc:
            logger.error("TypeTextAction error: %s", exc)


class KeyPressAction(PluginAction):
    action_id = "key_press"
    name = "Key Press"
    description = "Press a single key"
    can_configure = True

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        try:
            cfg = _parse_config(self.configuration)
            key = cfg.get("key", "").strip().lower()
            if key:
                injector.press(key)
        except Exception as exc:
            logger.error("KeyPressAction error: %s", exc)


class Main(IMacroDeckPlugin):
    package_id = "builtin.keyboard"
    name = "Keyboard"
    version = "1.0.0"
    author = "MacroDeck"
    description = "Built-in keyboard / hotkey actions"
    can_configure = False

    def enable(self) -> None:
        self.actions: List[PluginAction] = [
            HotkeyAction(),
            TypeTextAction(),
            KeyPressAction(),
        ]