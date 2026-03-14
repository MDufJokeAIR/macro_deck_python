"""
keyboard_macro — Macro Deck Python Extension
=============================================
Inject keyboard macros of 1–5 keys with:
  • Short press  (tap — configurable hold duration, default 50 ms)
  • Long press   (hold for a configurable duration, default 500 ms)
  • Double-click (two rapid taps, configurable interval)

Actions exposed:
  macro_short_press   — send a 1–5-key combo as a short tap
  macro_long_press    — hold the combo for N ms
  macro_double_click  — send the combo twice in quick succession
  macro_hold_down     — hold all keys until macro_release is triggered
  macro_release       — release all currently held keys
  macro_tap_sequence  — send up to 5 combos in sequence with delays

Configuration JSON schema (shared across actions):
  {
    "keys":         ["ctrl", "shift", "t"],  // 1–5 keys
    "hold_ms":      500,                     // long-press duration (ms)
    "double_interval_ms": 100,               // gap between two taps
    "tap_ms":       50,                      // short-press hold time
    "repeat":       1,                       // how many times to repeat
    "delay_before_ms": 0,                    // wait before sending
    "delay_after_ms":  0                     // wait after sending
  }

For macro_tap_sequence, keys is an array of arrays:
  { "sequence": [["ctrl","c"], ["ctrl","v"]], "step_delay_ms": 100 }
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from macro_deck_python.sdk import PluginBase, ActionBase
from macro_deck_python.plugins.builtin.keyboard_macro import injector
from macro_deck_python.plugins.builtin.keyboard_macro.key_map import (
    KEY_MAP, KEY_GROUPS, ALIASES, resolve, label, all_key_names,
)

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton

logger = logging.getLogger("plugin.keyboard_macro")

# Keys currently held via macro_hold_down (protected by lock)
_held_lock = threading.Lock()
_held_keys: List[str] = []


# ═══════════════════════════════════════════════════════════════════════
# Config helper
# ═══════════════════════════════════════════════════════════════════════

def _parse(configuration: str) -> Dict[str, Any]:
    try:
        return json.loads(configuration) if configuration else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _keys(cfg: Dict) -> List[str]:
    """Extract and validate the key list from config (1–5 entries)."""
    raw = cfg.get("keys", [])
    if isinstance(raw, str):
        raw = [raw]
    validated = []
    for k in raw[:5]:
        k = str(k).lower().strip()
        k = ALIASES.get(k, k)
        if k in KEY_MAP:
            validated.append(k)
        else:
            logger.warning("Unknown key ignored: %r", k)
    return validated


# ═══════════════════════════════════════════════════════════════════════
# Individual action classes
# ═══════════════════════════════════════════════════════════════════════

class ShortPressAction(ActionBase):
    """
    Send a 1–5-key combo as a short tap.

    Config:
      keys            list of 1–5 key names
      tap_ms          how long to hold before releasing  (default 50)
      repeat          how many times to repeat           (default 1)
      delay_before_ms wait before first tap              (default 0)
      delay_after_ms  wait after last tap                (default 0)
    """
    action_id     = "macro_short_press"
    name          = "Short Press (1–5 keys)"
    description   = "Tap a combo of 1–5 keys. Supports modifiers, F-keys, OEM, media keys."
    can_configure = True

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        cfg     = _parse(self.configuration)
        keys    = _keys(cfg)
        if not keys:
            logger.warning("ShortPress: no valid keys configured")
            return
        tap_ms          = max(1, int(cfg.get("tap_ms", 50)))
        repeat          = max(1, int(cfg.get("repeat", 1)))
        delay_before_ms = max(0, int(cfg.get("delay_before_ms", 0)))
        delay_after_ms  = max(0, int(cfg.get("delay_after_ms", 0)))

        if delay_before_ms:
            time.sleep(delay_before_ms / 1000.0)

        for i in range(repeat):
            if len(keys) == 1:
                injector.down(keys[0])
                time.sleep(tap_ms / 1000.0)
                injector.up(keys[0])
            else:
                # Hold modifiers, tap the last key
                for k in keys[:-1]:
                    injector.down(k)
                injector.down(keys[-1])
                time.sleep(tap_ms / 1000.0)
                injector.up(keys[-1])
                for k in reversed(keys[:-1]):
                    injector.up(k)
            if i < repeat - 1:
                time.sleep(tap_ms / 1000.0)   # inter-repeat gap

        if delay_after_ms:
            time.sleep(delay_after_ms / 1000.0)

        logger.debug("ShortPress: %s × %d", keys, repeat)


class LongPressAction(ActionBase):
    """
    Hold a 1–5-key combo for a configurable duration.

    Config:
      keys      list of 1–5 key names
      hold_ms   how long to hold (default 500)
      repeat    how many times to repeat (default 1)
      delay_before_ms / delay_after_ms
    """
    action_id     = "macro_long_press"
    name          = "Long Press (1–5 keys)"
    description   = "Hold a combo of 1–5 keys for a configurable duration."
    can_configure = True

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        cfg     = _parse(self.configuration)
        keys    = _keys(cfg)
        if not keys:
            logger.warning("LongPress: no valid keys configured")
            return
        hold_ms         = max(1, int(cfg.get("hold_ms", 500)))
        repeat          = max(1, int(cfg.get("repeat", 1)))
        delay_before_ms = max(0, int(cfg.get("delay_before_ms", 0)))
        delay_after_ms  = max(0, int(cfg.get("delay_after_ms", 0)))

        if delay_before_ms:
            time.sleep(delay_before_ms / 1000.0)

        for i in range(repeat):
            for k in keys:
                injector.down(k)
            time.sleep(hold_ms / 1000.0)
            for k in reversed(keys):
                injector.up(k)
            if i < repeat - 1:
                time.sleep(50 / 1000.0)

        if delay_after_ms:
            time.sleep(delay_after_ms / 1000.0)

        logger.debug("LongPress: %s for %dms × %d", keys, hold_ms, repeat)


class DoubleClickAction(ActionBase):
    """
    Send a 1–5-key combo twice in quick succession.

    Config:
      keys                 list of 1–5 key names
      double_interval_ms   gap between the two taps (default 80)
      tap_ms               individual tap hold time (default 50)
      delay_before_ms / delay_after_ms
    """
    action_id     = "macro_double_click"
    name          = "Double Click (1–5 keys)"
    description   = "Send a key combo twice rapidly — like a double-click."
    can_configure = True

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        cfg      = _parse(self.configuration)
        keys     = _keys(cfg)
        if not keys:
            logger.warning("DoubleClick: no valid keys configured")
            return
        tap_ms              = max(1,  int(cfg.get("tap_ms", 50)))
        interval_ms         = max(10, int(cfg.get("double_interval_ms", 80)))
        delay_before_ms     = max(0,  int(cfg.get("delay_before_ms", 0)))
        delay_after_ms      = max(0,  int(cfg.get("delay_after_ms", 0)))

        if delay_before_ms:
            time.sleep(delay_before_ms / 1000.0)

        for _ in range(2):
            if len(keys) == 1:
                injector.down(keys[0])
                time.sleep(tap_ms / 1000.0)
                injector.up(keys[0])
            else:
                for k in keys[:-1]: injector.down(k)
                injector.down(keys[-1])
                time.sleep(tap_ms / 1000.0)
                injector.up(keys[-1])
                for k in reversed(keys[:-1]): injector.up(k)
            time.sleep(interval_ms / 1000.0)

        if delay_after_ms:
            time.sleep(delay_after_ms / 1000.0)

        logger.debug("DoubleClick: %s (interval %dms)", keys, interval_ms)


class HoldDownAction(ActionBase):
    """
    Hold 1–5 keys until macro_release is triggered.
    Useful for push-to-talk, push-to-mute, etc.

    Config:
      keys   list of 1–5 key names
    """
    action_id     = "macro_hold_down"
    name          = "Hold Down (1–5 keys)"
    description   = "Hold keys until 'Release Held Keys' is triggered."
    can_configure = True

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        cfg  = _parse(self.configuration)
        keys = _keys(cfg)
        if not keys:
            logger.warning("HoldDown: no valid keys configured")
            return
        with _held_lock:
            # Release any previously held keys first
            for k in reversed(_held_keys):
                try: injector.up(k)
                except Exception: pass
            _held_keys.clear()
            for k in keys:
                injector.down(k)
            _held_keys.extend(keys)
        logger.debug("HoldDown: %s", keys)


class ReleaseAction(ActionBase):
    """
    Release all keys currently held by macro_hold_down.
    No configuration needed.
    """
    action_id     = "macro_release"
    name          = "Release Held Keys"
    description   = "Release all keys currently held by 'Hold Down'."
    can_configure = False

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        with _held_lock:
            for k in reversed(_held_keys):
                try: injector.up(k)
                except Exception: pass
            count = len(_held_keys)
            _held_keys.clear()
        logger.debug("Released %d held key(s)", count)


class TapSequenceAction(ActionBase):
    """
    Send up to 5 combos in sequence, with configurable delays between steps.

    Config:
      sequence        array of up to 5 key-name arrays
                      e.g. [["ctrl","c"], ["ctrl","v"]]
      step_delay_ms   delay between each combo (default 50)
      tap_ms          hold time per combo (default 50)
      delay_before_ms / delay_after_ms
    """
    action_id     = "macro_tap_sequence"
    name          = "Tap Sequence (up to 5 combos)"
    description   = "Send up to 5 key combos in sequence with configurable delays."
    can_configure = True

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        cfg             = _parse(self.configuration)
        raw_seq         = cfg.get("sequence", [])
        step_delay_ms   = max(0, int(cfg.get("step_delay_ms", 50)))
        tap_ms          = max(1, int(cfg.get("tap_ms", 50)))
        delay_before_ms = max(0, int(cfg.get("delay_before_ms", 0)))
        delay_after_ms  = max(0, int(cfg.get("delay_after_ms", 0)))

        if not raw_seq:
            logger.warning("TapSequence: empty sequence")
            return

        if delay_before_ms:
            time.sleep(delay_before_ms / 1000.0)

        for i, step in enumerate(raw_seq[:5]):
            if isinstance(step, str):
                step = [step]
            step_keys = _keys({"keys": step})
            if not step_keys:
                logger.warning("TapSequence step %d: no valid keys", i)
                continue

            if len(step_keys) == 1:
                injector.down(step_keys[0])
                time.sleep(tap_ms / 1000.0)
                injector.up(step_keys[0])
            else:
                for k in step_keys[:-1]: injector.down(k)
                injector.down(step_keys[-1])
                time.sleep(tap_ms / 1000.0)
                injector.up(step_keys[-1])
                for k in reversed(step_keys[:-1]): injector.up(k)

            if i < len(raw_seq) - 1 and step_delay_ms:
                time.sleep(step_delay_ms / 1000.0)

        if delay_after_ms:
            time.sleep(delay_after_ms / 1000.0)

        logger.debug("TapSequence: %d step(s)", len(raw_seq))


# ═══════════════════════════════════════════════════════════════════════
# Main plugin
# ═══════════════════════════════════════════════════════════════════════

class Main(PluginBase):
    package_id  = "builtin.keyboard_macro"
    name        = "Keyboard Macro"
    version     = "1.0.0"
    author      = "MacroDeck"
    description = (
        "Inject keyboard macros of 1–5 keys. "
        "Supports short press, long press, double-click, hold-down/release, and tap sequences. "
        "Works on Windows (SendInput), macOS (Quartz), Linux (xdotool/Xlib/evdev/pyautogui)."
    )
    can_configure = False

    def enable(self) -> None:
        super().enable()   # no @action decorators, all class-style
        self.actions = [
            ShortPressAction(),
            LongPressAction(),
            DoubleClickAction(),
            HoldDownAction(),
            ReleaseAction(),
            TapSequenceAction(),
        ]
        # Prime the backend detection at load time so first press is instant
        try:
            injector._init_backend()
            self.log_info(
                f"Keyboard macro plugin ready — "
                f"backend: {type(injector._backend).__name__}"
            )
        except Exception as exc:
            self.log_warning(f"Keyboard backend not yet available: {exc}")

    def disable(self) -> None:
        # Safety: release everything on shutdown
        with _held_lock:
            for k in reversed(_held_keys):
                try: injector.up(k)
                except Exception: pass
            _held_keys.clear()
        self.log_info("Keyboard macro plugin disabled")
