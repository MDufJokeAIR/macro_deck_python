"""
MacroKeys Plugin  —  Keyboard macro injection for Macro Deck Python
====================================================================

Actions
-------
  macro_keys          Inject a macro of 1–5 keys with optional modifiers.
  key_sequence        Press keys one after another (not simultaneously).

Configuration JSON schema  (macro_keys)
---------------------------------------
{
  "keys": [
    {
      "key":        "a",            // label from key_map.BY_LABEL (required)
      "press_type": "short",        // "short" | "long" | "double"
      "hold_ms":    30,             // ms to hold for "short" (default 30)
      "long_ms":    500,            // ms to hold for "long" (default 500)
      "double_interval_ms": 80      // ms between the two presses for "double"
    },
    // … up to 5 entries
  ],
  "mode": "combo",                  // "combo" = all keys simultaneously
                                    // "sequence" = one after another
  "sequence_delay_ms": 50           // delay between keys in sequence mode
}

Examples
--------
Ctrl+C  (combo, short):
  {"keys": [{"key":"Left Ctrl"},{"key":"c"}], "mode":"combo"}

Alt+F4  (combo, short):
  {"keys": [{"key":"Left Alt"},{"key":"F4"}], "mode":"combo"}

Double-click Ctrl+Z (undo twice):
  {"keys": [{"key":"Left Ctrl"},{"key":"z","press_type":"double"}], "mode":"combo"}

Long press Win key:
  {"keys": [{"key":"Left Win/⌘","press_type":"long","long_ms":1000}], "mode":"combo"}

Type sequence a → b → c:
  {"keys": [{"key":"a"},{"key":"b"},{"key":"c"}], "mode":"sequence"}
"""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional, TYPE_CHECKING

from macro_deck_python.sdk import PluginBase, ActionBase
from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import (
    ALL_KEYS, BY_LABEL, BY_GROUP, GROUPS, KeyDef,
)
from macro_deck_python.plugins.builtin.macro_keys_plugin.key_injector import (
    press_combination, press_key, key_down, key_up,
)

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton

logger = logging.getLogger("plugin.macro_keys")


# ════════════════════════════════════════════════════════════════════
# Configuration helpers
# ════════════════════════════════════════════════════════════════════

_DEFAULT_SHORT_MS     = 30
_DEFAULT_LONG_MS      = 500
_DEFAULT_DOUBLE_MS    = 80
_DEFAULT_SEQ_DELAY_MS = 50
_MAX_KEYS             = 5


def _parse_key_entry(entry: dict) -> Optional[KeyDef]:
    """Resolve a config dict entry to a KeyDef, or None if unknown."""
    label = entry.get("key", "")
    kd = BY_LABEL.get(label)
    if kd is None:
        logger.warning("Unknown key label: %r — skipped", label)
    return kd


def _do_single_key(kd: KeyDef, press_type: str,
                   hold_ms: int, long_ms: int, double_ms: int) -> None:
    """Inject a single key with the given press_type."""
    if press_type == "long":
        key_down(kd)
        time.sleep(long_ms / 1000.0)
        key_up(kd)

    elif press_type == "double":
        press_key(kd)
        time.sleep(double_ms / 1000.0)
        press_key(kd)

    else:  # "short" (default)
        press_key(kd)


def _do_combo(key_defs: list[KeyDef], press_types: list[str],
              hold_ms: int, long_ms: int, double_ms: int) -> None:
    """
    Press all keys together.
    If all press_types are "short":  standard press_combination().
    If the LAST key is "long":       hold combo for long_ms.
    If the LAST key is "double":     combo twice.
    Modifiers (non-last keys) always follow the main key's press_type.
    """
    if not key_defs:
        return

    main_type = press_types[-1] if press_types else "short"

    if main_type == "long":
        for kd in key_defs:
            key_down(kd)
        time.sleep(long_ms / 1000.0)
        for kd in reversed(key_defs):
            key_up(kd)

    elif main_type == "double":
        press_combination(key_defs, hold_ms)
        time.sleep(double_ms / 1000.0)
        press_combination(key_defs, hold_ms)

    else:  # short
        press_combination(key_defs, hold_ms)


def _execute_config(cfg: dict) -> None:
    """Parse and execute a macro_keys configuration dict."""
    raw_keys        = cfg.get("keys", [])[:_MAX_KEYS]
    mode            = cfg.get("mode", "combo")
    seq_delay_ms    = int(cfg.get("sequence_delay_ms", _DEFAULT_SEQ_DELAY_MS))

    if not raw_keys:
        logger.warning("MacroKeys: no keys configured")
        return

    # Resolve key entries
    entries: list[tuple[KeyDef, str, int, int, int]] = []
    for entry in raw_keys:
        kd = _parse_key_entry(entry)
        if kd is None:
            continue
        press_type = entry.get("press_type", "short")
        hold_ms    = int(entry.get("hold_ms",   _DEFAULT_SHORT_MS))
        long_ms    = int(entry.get("long_ms",   _DEFAULT_LONG_MS))
        double_ms  = int(entry.get("double_interval_ms", _DEFAULT_DOUBLE_MS))
        entries.append((kd, press_type, hold_ms, long_ms, double_ms))

    if not entries:
        return

    if mode == "sequence":
        # Press each key individually in order
        for i, (kd, press_type, hold_ms, long_ms, double_ms) in enumerate(entries):
            _do_single_key(kd, press_type, hold_ms, long_ms, double_ms)
            if i < len(entries) - 1:
                time.sleep(seq_delay_ms / 1000.0)

    else:  # combo (default)
        key_defs    = [e[0] for e in entries]
        press_types = [e[1] for e in entries]
        hold_ms     = entries[0][2]   # use first entry's hold_ms for the combo
        long_ms     = entries[-1][3]  # use last (main) key's long_ms
        double_ms   = entries[-1][4]
        _do_combo(key_defs, press_types, hold_ms, long_ms, double_ms)


# ════════════════════════════════════════════════════════════════════
# Actions
# ════════════════════════════════════════════════════════════════════

class MacroKeysAction(ActionBase):
    """
    Inject a macro of 1–5 keys (combo or sequence),
    each with short / long / double press support.
    """
    action_id     = "macro_keys"
    name          = "Macro Keys (1–5)"
    description   = (
        "Inject a keyboard macro: up to 5 keys simultaneously or in sequence, "
        "each with short press, long press, or double-click."
    )
    can_configure = True

    # Schema exposed to the configurator UI via REST
    config_schema = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["combo", "sequence"],
                "default": "combo",
                "description": "combo = all keys at once | sequence = one after another",
            },
            "sequence_delay_ms": {
                "type": "integer", "default": 50,
                "description": "Delay (ms) between keys in sequence mode",
            },
            "keys": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "required": ["key"],
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Key label (see /api/plugins/macrokeys/keys)",
                        },
                        "press_type": {
                            "type": "string",
                            "enum": ["short", "long", "double"],
                            "default": "short",
                        },
                        "hold_ms": {
                            "type": "integer", "default": 30,
                            "description": "Hold duration (ms) for short press",
                        },
                        "long_ms": {
                            "type": "integer", "default": 500,
                            "description": "Hold duration (ms) for long press",
                        },
                        "double_interval_ms": {
                            "type": "integer", "default": 80,
                            "description": "Interval (ms) between the two presses for double-click",
                        },
                    },
                },
            },
        },
    }

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        try:
            cfg = json.loads(self.configuration) if self.configuration else {}
        except json.JSONDecodeError as exc:
            logger.error("MacroKeysAction: invalid JSON config: %s", exc)
            return
        try:
            _execute_config(cfg)
        except Exception as exc:
            logger.error("MacroKeysAction execution error: %s", exc, exc_info=True)


class KeySequenceAction(ActionBase):
    """
    Type a plain text string key-by-key (convenience wrapper).
    Configuration: {"text": "Hello World", "delay_ms": 20}
    """
    action_id     = "key_sequence_text"
    name          = "Type Text (key-by-key)"
    description   = "Type a text string by injecting individual key presses."
    can_configure = True

    def trigger(self, client_id: str, button: "ActionButton") -> None:
        try:
            cfg  = json.loads(self.configuration) if self.configuration else {}
            text = cfg.get("text", "")
            delay_ms = int(cfg.get("delay_ms", 20))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("KeySequenceAction: bad config: %s", exc)
            return

        for char in text:
            kd = BY_LABEL.get(char) or BY_LABEL.get(char.lower())
            if kd:
                press_key(kd)
            else:
                # Unknown char — try direct injection via backend
                try:
                    _execute_config({"keys": [{"key": char}], "mode": "combo"})
                except Exception:
                    logger.debug("Cannot inject char %r", char)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)


# ════════════════════════════════════════════════════════════════════
# Plugin entry point
# ════════════════════════════════════════════════════════════════════

class Main(PluginBase):
    package_id  = "builtin.macro_keys"
    name        = "Macro Keys"
    version     = "1.0.0"
    author      = "MacroDeck"
    description = (
        "Inject keyboard macros of 1–5 keys with short/long/double press. "
        "Supports F1–F24, media, browser, OEM, numpad and all standard keys."
    )
    can_configure = False

    # ── expose key catalogue as plugin attribute ──────────────────
    all_keys  = ALL_KEYS
    by_label  = BY_LABEL
    by_group  = BY_GROUP
    groups    = GROUPS

    def enable(self) -> None:
        super().enable()   # no @action decorators on Main itself
        self.actions: List[ActionBase] = [
            MacroKeysAction(),
            KeySequenceAction(),
        ]
        try:
            from macro_deck_python.plugins.builtin.macro_keys_plugin.key_injector import (
                _detect_backend,
            )
            backend = _detect_backend()
            self.log_info(f"Backend: {backend}  |  {len(ALL_KEYS)} keys available")
        except ImportError as exc:
            self.log_warning(f"No key injection backend: {exc}")

    def disable(self) -> None:
        self.log_info("MacroKeys unloaded")
