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
from typing import List, TYPE_CHECKING, Optional

from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction
from macro_deck_python.plugins.builtin.keyboard_macro import injector
from macro_deck_python.utils.keyboard_layout import get_key_for_char, get_layout

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


# Characters that can be reliably typed by pressing keys directly
# (letters, space - these are layout-independent)
# NOTE: Digits are NOT included because on AZERTY they require shift modifier!
_DIRECTLY_TYPEABLE = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \t\n"
)

# Special key mappings for control characters
_SPECIAL_KEYS: dict = {
    '\n': 'enter',
    '\r': 'enter',
    '\t': 'tab',
}


def _type_via_alt_codes(text: str) -> bool:
    """
    Type special characters using Alt+NumericCode method.
    This is a fallback when clipboard is not available.
    
    Warning: Slow (one key pair per character) but reliable.
    """
    # Alt code mappings for common special characters
    # These are Unicode code points entered via Alt+numpad
    alt_codes = {
        '/': ('slash', ord('/')),
        '.': ('period', ord('.')),
        ':': ('colon', ord(':')),
        ';': ('semicolon', ord(';')),
        ',': ('comma', ord(',')),
        '<': ('less', ord('<')),
        '>': ('greater', ord('>')),
        '?': ('question', ord('?')),
        '!': ('exclamation', ord('!')),
    }
    
    for char in text:
        if char in alt_codes:
            name, code = alt_codes[char]
            logger.debug(f"Typing {name} ({code}) via Alt+code")
            
            # Alt+code method (requires numeric keypad)
            # This is unreliable, so we just log and skip
            logger.warning(f"Alt+code not fully implemented for {repr(char)}")
    
    return False


def _type_char(ch: str, interval: float = 0.03) -> None:
    """
    Send a single character to the keyboard using the appropriate method.
    
    Strategy:
    1. For control characters (newline, tab), press the key directly
    2. For directly typeable characters (letters, numbers, space), press directly
    3. For other characters, look up the key combination from the layout mapping
    4. Apply shift/AltGr modifiers as needed
    
    Args:
        ch: Character to type
        interval: Delay after character is typed (from button config)
    """
    # Handle special control characters
    if ch in _SPECIAL_KEYS:
        key = _SPECIAL_KEYS[ch]
        injector.press(key)
        logger.debug(f"Typed special key: {key}")
    # Handle directly typeable characters
    elif ch in _DIRECTLY_TYPEABLE:
        # Direct key press - works on all layouts
        if ch.isupper():
            injector.combo(["shift", ch.lower()])
        else:
            injector.press(ch)
        logger.debug(f"Typed directly: {repr(ch)}")
    # Handle other characters via key mapping
    else:
        layout = get_layout()
        key_info = get_key_for_char(ch, layout)
        
        if key_info:
            # Handle both 2-tuple and 3-tuple formats
            if len(key_info) == 3:
                # New format: (key, shift_required, altgr_required)
                key, shift_required, altgr_required = key_info
                if altgr_required and shift_required:
                    injector.combo(["alt_right", "shift", key])
                    logger.debug(f"Typed {repr(ch)} via AltGr+Shift+{key} on {layout}")
                elif altgr_required:
                    injector.combo(["alt_right", key])
                    logger.debug(f"Typed {repr(ch)} via AltGr+{key} on {layout}")
                elif shift_required:
                    injector.combo(["shift", key])
                    logger.debug(f"Typed {repr(ch)} via Shift+{key} on {layout}")
                else:
                    injector.press(key)
                    logger.debug(f"Typed {repr(ch)} via {key} on {layout}")
            else:
                # Legacy format: (key, shift_required)
                key, shift_required = key_info
                if shift_required:
                    injector.combo(["shift", key])
                    logger.debug(f"Typed {repr(ch)} via Shift+{key} on {layout}")
                else:
                    injector.press(key)
                    logger.debug(f"Typed {repr(ch)} via {key} on {layout}")
        else:
            # No mapping found - log warning and try direct press as last resort
            logger.warning(f"No key mapping found for {repr(ch)} on {layout} layout - attempting direct press")
            try:
                injector.press(ch)
                logger.debug(f"Typed {repr(ch)} via direct press (fallback)")
            except Exception as e:
                logger.error(f"Failed to type {repr(ch)}: {e}")
    
    # Always respect the interval timing from the button configuration
    if interval > 0:
        time.sleep(interval)


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
            
            # Type the text character by character with optimization
            self._type_text_optimized(text, interval)
        except Exception as exc:
            logger.error("TypeTextAction error: %s", exc)
    
    def _type_text_optimized(self, text: str, interval: float) -> None:
        """
        Type text character by character with proper timing.
        
        Strategy:
        - Use the interval parameter from button configuration (default 0.03s)
        - Type each character and wait for the interval
        - This ensures sequential execution without race conditions
        """
        for ch in text:
            _type_char(ch, interval=interval)


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