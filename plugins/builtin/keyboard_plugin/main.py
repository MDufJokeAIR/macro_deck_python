"""
Built-in plugin: keyboard actions.
Mirrors common built-in actions in Macro Deck (key press, type text, hotkey).
Requires: pyautogui
"""
from __future__ import annotations
import json
import logging
from typing import List, TYPE_CHECKING

from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton

logger = logging.getLogger("plugin.keyboard")


class HotkeyAction(PluginAction):
    action_id = "hotkey"
    name = "Press Hotkey"
    description = "Simulate a keyboard hotkey (e.g. ctrl+c)"
    can_configure = True

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        try:
            import pyautogui
        except ImportError:
            logger.error("pyautogui not installed; keyboard actions disabled")
            return
        try:
            cfg = json.loads(self.configuration) if self.configuration else {}
            keys = cfg.get("keys", "")
            if keys:
                parts = [k.strip() for k in keys.split("+")]
                pyautogui.hotkey(*parts)
        except Exception as exc:
            logger.error("HotkeyAction error: %s", exc)


class TypeTextAction(PluginAction):
    action_id = "type_text"
    name = "Type Text"
    description = "Type a string of text"
    can_configure = True

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        try:
            import pyautogui
        except ImportError:
            logger.error("pyautogui not installed; keyboard actions disabled")
            return
        try:
            cfg = json.loads(self.configuration) if self.configuration else {}
            text = cfg.get("text", "")
            interval = float(cfg.get("interval", 0.0))
            if text:
                pyautogui.typewrite(text, interval=interval)
        except Exception as exc:
            logger.error("TypeTextAction error: %s", exc)


class KeyPressAction(PluginAction):
    action_id = "key_press"
    name = "Key Press"
    description = "Press a single key"
    can_configure = True

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        try:
            import pyautogui
        except ImportError:
            return
        try:
            cfg = json.loads(self.configuration) if self.configuration else {}
            key = cfg.get("key", "")
            if key:
                pyautogui.press(key)
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
