"""
analog_slider — Macro Deck Python Extension
===========================================
Replace 1–N consecutive button cells in a column with a vertical analog slider.

Architecture
------------
  SliderConfig    — immutable config: size, range, step, outputs list
  SliderState     — mutable live state: current value, output engines, throttle
  SliderRegistry  — global registry  slider_id → SliderState
  AnalogOutput    — abstract output backend (variable, key_threshold, …)

Slider storage
--------------
Sliders are stored directly as ActionButton objects inside the normal grid:

  button_type="slider"          ← the head cell (row_start, col)
    slider_config = { size, min_value, max_value, step, label, color,
                      outputs: [{type, ...}, ...], current_value }

  button_type="slider_occupied" ← every subsequent cell in the same column
    slider_config = { parent_id: <head button_id>, parent_pos: "row_col" }

Actions
-------
  create_slider       — place a slider in a column at row/col
  remove_slider       — remove a slider and its occupied cells
  set_slider_value    — set a specific slider to a value programmatically

WebSocket
---------
  Registers a SLIDER_CHANGE hook via MacroDeckServer.register_message_hook()
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from macro_deck_python.models.action_button import ActionButton
from macro_deck_python.plugins.builtin.analog_slider.analog_output import (
    AnalogOutput, make_output,
)
from macro_deck_python.sdk import PluginBase, ActionBase

if TYPE_CHECKING:
    pass

logger = logging.getLogger("plugin.analog_slider")


# ═══════════════════════════════════════════════════════════════════════
# SliderConfig — per-slider configuration
# ═══════════════════════════════════════════════════════════════════════

class SliderConfig:
    """
    Immutable(ish) slider configuration object.

    Parameters accepted in the dict constructor:
      size            int    rows occupied  (default 3, min 1)
      orientation     str    "vertical" | "horizontal" (default "vertical")
      min_value       float  minimum value (default 0.0)
      max_value       float  maximum value (default 100.0)
      step            float  snap step; 0 = no snapping (default 1.0)
      label           str    display label (default "")
      label_show_value bool  append current value to label (default True)
      value_format    str    Python format string for value, e.g. "{:.1f}%" (default "{:.0f}")
      color           str    CSS colour for the track (default "#7c83fd")
      outputs         list   list of output config dicts
    """

    def __init__(self, cfg: dict):
        self.size:             int   = max(1, int(cfg.get("size", 3)))
        self.orientation:      str   = cfg.get("orientation", "vertical")
        self.min_value:        float = float(cfg.get("min_value", 0.0))
        self.max_value:        float = float(cfg.get("max_value", 100.0))
        self.step:             float = float(cfg.get("step", 1.0))
        self.label:            str   = cfg.get("label", "")
        self.label_show_value: bool  = bool(cfg.get("label_show_value", True))
        self.value_format:     str   = cfg.get("value_format", "{:.0f}")
        self.color:            str   = cfg.get("color", "#7c83fd")
        self.outputs:          list  = list(cfg.get("outputs", []))
        self.current_value:    float = float(cfg.get("current_value", self.min_value))

    # ── value helpers ─────────────────────────────────────────────────

    def snap(self, value: float) -> float:
        """Round *value* to the nearest step and clamp to [min, max]."""
        lo, hi = self.min_value, self.max_value
        clamped = max(lo, min(hi, value))
        if self.step <= 0:
            return clamped
        # Round to nearest multiple of step relative to min_value
        steps = math.floor((clamped - lo) / self.step + 0.5)  # round-half-up
        snapped = lo + steps * self.step
        return max(lo, min(hi, snapped))

    def normalised(self, value: float) -> float:
        span = self.max_value - self.min_value
        if span == 0:
            return 0.0
        return (value - self.min_value) / span

    def display_label(self) -> str:
        if self.label_show_value:
            val_str = self.value_format.format(self.current_value)
            return f"{self.label}\n{val_str}" if self.label else val_str
        return self.label

    # ── serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "size":             self.size,
            "orientation":      self.orientation,
            "min_value":        self.min_value,
            "max_value":        self.max_value,
            "step":             self.step,
            "label":            self.label,
            "label_show_value": self.label_show_value,
            "value_format":     self.value_format,
            "color":            self.color,
            "outputs":          self.outputs,
            "current_value":    self.current_value,
        }

    def build_state(self, slider_id: str,
                    throttle_ms: int = 16) -> "SliderState":
        """Instantiate a SliderState from this config."""
        output_pairs: List[Tuple[AnalogOutput, dict]] = []
        for out_cfg in self.outputs:
            out_type = out_cfg.get("type", "variable")
            engine = make_output(out_type)
            if engine:
                output_pairs.append((engine, out_cfg))
        return SliderState(
            slider_id   = slider_id,
            current     = self.snap(self.current_value),
            outputs     = output_pairs,
            min_value   = self.min_value,
            max_value   = self.max_value,
            throttle_ms = throttle_ms,
        )


# ═══════════════════════════════════════════════════════════════════════
# SliderState — live runtime state for one slider
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SliderState:
    slider_id:   str
    current:     float
    outputs:     List[Tuple[AnalogOutput, dict]]
    min_value:   float
    max_value:   float
    throttle_ms: int  = 16      # ~60 fps max send rate; 0 = unlimited
    _last_apply: float = field(default=0.0, repr=False)
    _pending:    bool  = field(default=False, repr=False)
    _lock:       Any   = field(default_factory=threading.Lock, repr=False)

    def normalised(self) -> float:
        span = self.max_value - self.min_value
        if span == 0:
            return 0.0
        return (self.current - self.min_value) / span

    def clamp(self, value: float) -> float:
        return max(self.min_value, min(self.max_value, value))

    def apply_outputs(self, value: float) -> None:
        """Apply value to all registered outputs."""
        n = self.normalised()
        for engine, cfg in self.outputs:
            try:
                engine.apply(value, n, cfg)
            except Exception as exc:
                logger.error("Output error [%s]: %s", engine.__class__.__name__, exc)

    def cleanup(self) -> None:
        for engine, _ in self.outputs:
            try:
                engine.cleanup()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════
# SliderRegistry — global singleton
# ═══════════════════════════════════════════════════════════════════════

class _SlidersMeta(type):
    """
    Metaclass that exposes _sliders and _broadcast_cb as transparent
    class-level attributes pointing directly into the registry module.
    This allows tests to do SliderRegistry._sliders and
    SliderRegistry._broadcast_cb = None without going through descriptors.
    """
    @property
    def _sliders(cls):
        from macro_deck_python.plugins.builtin.analog_slider import registry as _r
        return _r._SLIDERS

    @_sliders.setter
    def _sliders(cls, value):
        from macro_deck_python.plugins.builtin.analog_slider import registry as _r
        _r._SLIDERS.clear()
        _r._SLIDERS.update(value)

    @property
    def _broadcast_cb(cls):
        from macro_deck_python.plugins.builtin.analog_slider import registry as _r
        return _r._BROADCAST_CB

    @_broadcast_cb.setter
    def _broadcast_cb(cls, value):
        from macro_deck_python.plugins.builtin.analog_slider import registry as _r
        _r._BROADCAST_CB = value


class SliderRegistry(metaclass=_SlidersMeta):
    """
    Thin proxy to the stable registry module.
    The actual data lives in analog_slider.registry so it survives
    dynamic plugin reloads (the module stays in sys.modules).
    Direct attribute access (_sliders, _broadcast_cb) is handled by the metaclass.
    """

    @classmethod
    def _reg(cls):
        from macro_deck_python.plugins.builtin.analog_slider import registry as _r
        return _r

    @classmethod
    def register(cls, slider_id: str, state: "SliderState") -> None:
        cls._reg().register(slider_id, state)

    @classmethod
    def unregister(cls, slider_id: str) -> None:
        cls._reg().unregister(slider_id)

    @classmethod
    def get_state(cls, slider_id: str) -> Optional["SliderState"]:
        return cls._reg().get_state(slider_id)

    @classmethod
    def all_slider_ids(cls) -> List[str]:
        return cls._reg().all_slider_ids()

    @classmethod
    def set_broadcast_cb(cls, cb) -> None:
        cls._reg().set_broadcast_cb(cb)

    @classmethod
    def on_change(cls, slider_id: str, new_value: float) -> None:
        cls._reg().on_change(slider_id, new_value)


# ═══════════════════════════════════════════════════════════════════════
# WebSocket hook
# ═══════════════════════════════════════════════════════════════════════

async def _handle_slider_change(info, msg: dict) -> None:
    """Async handler for SLIDER_CHANGE WebSocket messages."""
    from macro_deck_python.websocket.protocol import encode
    from macro_deck_python.services.profile_manager import ProfileManager

    slider_id = msg.get("slider_id", "")
    raw_val   = msg.get("value")

    try:
        new_value = float(raw_val)
        if math.isnan(new_value) or math.isinf(new_value):
            raise ValueError("non-finite value")
    except (TypeError, ValueError) as exc:
        await info.ws.send(encode("ERROR",
                                  message=f"SLIDER_CHANGE invalid value: {exc}"))
        return

    # If not in registry, try to auto-load from active profile
    if SliderRegistry.get_state(slider_id) is None:
        try:
            profile = ProfileManager.get_client_profile(info.client_id)
            if profile:
                _reload_slider_from_profile(profile, slider_id)
        except Exception:
            pass

    # Fire on_change regardless — if still unknown, on_change is a no-op
    SliderRegistry.on_change(slider_id, new_value)

    # Persist new value back to profile (best-effort)
    try:
        profile = ProfileManager.get_client_profile(info.client_id)
        state   = SliderRegistry.get_state(slider_id)
        if profile and state:
            _update_current_value_in_profile(profile, slider_id, new_value, state)
    except Exception:
        pass


def _reload_slider_from_profile(profile, slider_id: str) -> None:
    """Find slider config in profile and (re-)register it."""
    for pos, btn in profile.folder.buttons.items():
        if btn.button_id == slider_id and btn.button_type == "slider":
            sc = SliderConfig(btn.slider_config)
            state = sc.build_state(slider_id)
            SliderRegistry.register(slider_id, state)
            return


def _update_current_value_in_profile(profile, slider_id: str,
                                      new_value: float, state: SliderState) -> None:
    """Persist snapped current_value back into the button's slider_config."""
    from macro_deck_python.services.profile_manager import ProfileManager
    for pos, btn in profile.folder.buttons.items():
        if btn.button_id == slider_id and btn.button_type == "slider":
            sc_dict = dict(btn.slider_config)
            sc = SliderConfig(sc_dict)
            snapped = sc.snap(new_value)
            sc_dict["current_value"] = snapped
            btn.slider_config = sc_dict
            state.current = state.clamp(snapped)
            try:
                ProfileManager.save()
            except Exception:
                pass
            return


def _register_ws_hook() -> None:
    """Register the SLIDER_CHANGE handler with the WebSocket server."""
    from macro_deck_python.websocket.server import MacroDeckServer
    MacroDeckServer.register_message_hook("SLIDER_CHANGE", _handle_slider_change)


# ═══════════════════════════════════════════════════════════════════════
# Actions
# ═══════════════════════════════════════════════════════════════════════

class CreateSliderAction(ActionBase):
    """
    Place a slider in the current profile's active folder.

    Config:
      row            int   starting row (0-based)
      col            int   column  (0-based)
      slider_config  dict  SliderConfig-compatible dict
    """
    action_id     = "create_slider"
    name          = "Create Slider"
    description   = "Replace cells in a column with an analog slider."
    can_configure = True

    def trigger(self, client_id: str, button) -> None:
        from macro_deck_python.services.profile_manager import ProfileManager
        cfg = json.loads(self.configuration) if self.configuration else {}
        row = int(cfg.get("row", 0))
        col = int(cfg.get("col", 0))
        sc_dict = dict(cfg.get("slider_config", {}))

        profile = ProfileManager.get_client_profile(client_id) or ProfileManager.get_active()
        if profile is None:
            logger.error("CreateSlider: no active profile")
            return

        sc = SliderConfig(sc_dict)

        # Create the head button
        head = ActionButton(
            button_type  = "slider",
            slider_config = {**sc.to_dict()},
        )
        profile.folder.set_button(row, col, head)

        # Create occupied cells
        for i in range(1, sc.size):
            occ = ActionButton(
                button_type  = "slider_occupied",
                slider_config = {
                    "parent_id":  head.button_id,
                    "parent_pos": f"{row}_{col}",
                },
            )
            profile.folder.set_button(row + i, col, occ)

        # Register in SliderRegistry
        state = sc.build_state(head.button_id)
        SliderRegistry.register(head.button_id, state)

        try:
            ProfileManager.save()
        except Exception:
            pass

        logger.info("Created slider %s at (%d,%d) size=%d",
                    head.button_id[:8], row, col, sc.size)


class RemoveSliderAction(ActionBase):
    """
    Remove a slider and clear all its occupied cells.

    Config:
      row  int  row of the slider head
      col  int  column of the slider
    """
    action_id     = "remove_slider"
    name          = "Remove Slider"
    description   = "Remove a slider and free its cells."
    can_configure = True

    def trigger(self, client_id: str, button) -> None:
        from macro_deck_python.services.profile_manager import ProfileManager
        cfg = json.loads(self.configuration) if self.configuration else {}
        row = int(cfg.get("row", 0))
        col = int(cfg.get("col", 0))

        profile = ProfileManager.get_client_profile(client_id) or ProfileManager.get_active()
        if profile is None:
            return

        head_btn = profile.folder.get_button(row, col)
        if head_btn is None or head_btn.button_type != "slider":
            return

        slider_id = head_btn.button_id
        size = head_btn.slider_config.get("size", 1)

        # Remove head + occupied cells
        profile.folder.remove_button(row, col)
        for i in range(1, size):
            profile.folder.remove_button(row + i, col)

        SliderRegistry.unregister(slider_id)

        try:
            ProfileManager.save()
        except Exception:
            pass

        logger.info("Removed slider %s at (%d,%d)", slider_id[:8], row, col)


class SetSliderValueAction(ActionBase):
    """
    Set a slider to a specific value.

    Config:
      slider_id  str    target slider button_id
      value      float  value to set
    """
    action_id     = "set_slider_value"
    name          = "Set Slider Value"
    description   = "Programmatically set a slider value."
    can_configure = True

    def trigger(self, client_id: str, button) -> None:
        cfg = json.loads(self.configuration) if self.configuration else {}
        slider_id = cfg.get("slider_id", "")
        if not slider_id:
            return
        try:
            value = float(cfg.get("value", 0))
        except (TypeError, ValueError):
            return
        SliderRegistry.on_change(slider_id, value)


# ═══════════════════════════════════════════════════════════════════════
# Main plugin
# ═══════════════════════════════════════════════════════════════════════

class Main(PluginBase):
    package_id  = "builtin.analog_slider"
    name        = "Analog Slider"
    version     = "1.0.0"
    author      = "MacroDeck"
    description = (
        "Replace button cells in a column with an analog slider. "
        "Outputs: variable, key_threshold. "
        "Actions: create_slider, remove_slider, set_slider_value."
    )
    can_configure = False

    def enable(self) -> None:
        super().enable()
        self.actions = [
            CreateSliderAction(),
            RemoveSliderAction(),
            SetSliderValueAction(),
        ]
        # Wire SLIDER_CHANGE into the WebSocket server
        _register_ws_hook()
        # Set broadcast callback so SliderRegistry can push SLIDER_STATE
        _register_broadcast()
        logger.info("Analog Slider plugin ready")

    def disable(self) -> None:
        # Unregister every slider from the registry
        for sid in SliderRegistry.all_slider_ids():
            SliderRegistry.unregister(sid)
        logger.info("Analog Slider plugin disabled")


def _unregister_all() -> None:
    ids = SliderRegistry.all_slider_ids()
    for sid in ids:
        SliderRegistry.unregister(sid)


def _register_broadcast() -> None:
    """Push SLIDER_STATE to all connected clients when a slider changes."""
    from macro_deck_python.websocket.server import MacroDeckServer
    from macro_deck_python.websocket.protocol import encode

    def _cb(slider_id: str, value: float) -> None:
        msg = encode("SLIDER_STATE", slider_id=slider_id, value=value)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    _broadcast_to_all(MacroDeckServer, msg)
                )
        except RuntimeError:
            pass

    SliderRegistry.set_broadcast_cb(_cb)


async def _broadcast_to_all(server_cls, msg: str) -> None:
    """Find running server instance and broadcast."""
    # Walk all running server instances via their _clients registry
    # (There's only one server per process)
    from macro_deck_python.websocket.server import MacroDeckServer
    # MacroDeckServer is not a singleton, but its _plugin_message_hooks is class-level.
    # We can't directly reach the instance, so we use the variable manager's
    # change callback mechanism to push to clients.
    # For now: no-op here — SLIDER_STATE is already pushed per on_change path.
    pass
