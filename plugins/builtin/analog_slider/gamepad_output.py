"""
gamepad_output.py  —  Virtual gamepad axis output for the Analog Slider plugin.

Uses the ``vgamepad`` package (which wraps the ViGEm Bus driver) to expose a
virtual Xbox 360 controller that Windows games see as a real gamepad.

Architecture
------------
A single ``_GamepadDevice`` singleton holds the one ``VX360Gamepad`` instance
and the current axis state dict.  All ``GamepadAxisOutput`` instances share it,
which is essential because vgamepad requires both X *and* Y to be passed in the
same call — so we must track the last value of every axis and re-send the pair
whenever either changes.

Axis names  (config key  ``axis``)
-----------------------------------
  left_x      Left stick, horizontal   (-1 = full left,  +1 = full right)
  left_y      Left stick, vertical     (-1 = full down,  +1 = full up)
  right_x     Right stick, horizontal
  right_y     Right stick, vertical
  trigger_l   Left trigger             ( 0 = released,    1 = fully pressed)
  trigger_r   Right trigger

Config keys (per output entry in slider_config["outputs"])
----------------------------------------------------------
  axis          str    one of the axis names above  (required)
  deadzone      float  ±fraction of center to clamp to 0.0  (default 0.05,
                        joystick axes only — ignored for triggers)
  invert        bool   flip the direction before writing  (default False)
  gamepad_index int    future use — always 0 for now

Graceful degradation
--------------------
If ``vgamepad`` is not importable (Linux / no ViGEm driver) every call is a
no-op and a one-time warning is logged.  The rest of the application continues
normally.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("plugin.analog_slider.gamepad")

# ── attempt to import vgamepad ────────────────────────────────────────────────
_VGAMEPAD_AVAILABLE = False
_vg = None
try:
    import vgamepad as _vg          # type: ignore
    _VGAMEPAD_AVAILABLE = True
except ImportError:
    logger.warning(
        "vgamepad not installed — gamepad axis output disabled. "
        "Install it with: pip install vgamepad  "
        "(also requires the ViGEm Bus driver on Windows)"
    )
except Exception as exc:
    logger.warning("vgamepad import error: %s — gamepad axis output disabled", exc)


# ── Joystick / trigger axis groups ───────────────────────────────────────────
_JOYSTICK_AXES = {"left_x", "left_y", "right_x", "right_y"}
_TRIGGER_AXES  = {"trigger_l", "trigger_r"}
_ALL_AXES      = _JOYSTICK_AXES | _TRIGGER_AXES


# ── Singleton gamepad device ──────────────────────────────────────────────────

class _GamepadDevice:
    """
    Holds the single VX360Gamepad and the last-known value of every axis.
    Thread-safe; all public methods acquire ``_lock``.
    """

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._pad   = None          # VX360Gamepad or None if unavailable
        self._state = {             # normalised values: joystick -1..+1, trigger 0..1
            "left_x":   0.0,
            "left_y":   0.0,
            "right_x":  0.0,
            "right_y":  0.0,
            "trigger_l": 0.0,
            "trigger_r": 0.0,
        }
        self._init_pad()

    def _init_pad(self) -> None:
        if not _VGAMEPAD_AVAILABLE or _vg is None:
            return
        try:
            self._pad = _vg.VX360Gamepad()
            self._pad.update()          # register with ViGEm
            logger.info("Virtual Xbox 360 gamepad created via ViGEm")
        except Exception as exc:
            self._pad = None
            logger.error("Could not create virtual gamepad: %s", exc)

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._pad is not None

    def set_axis(self, axis: str, value_float: float) -> None:
        """
        Update one axis and push the full state to ViGEm.

        ``value_float`` must already be in the correct range:
          -1.0 … +1.0  for joystick axes
           0.0 … 1.0   for trigger axes
        """
        if self._pad is None:
            return
        with self._lock:
            if axis not in self._state:
                logger.warning("Unknown gamepad axis: %r", axis)
                return
            self._state[axis] = value_float
            self._flush()

    def _flush(self) -> None:
        """Push full axis state to the virtual pad.  Must be called inside lock."""
        try:
            s = self._state
            self._pad.left_joystick_float(
                x_value_float=s["left_x"],
                y_value_float=s["left_y"],
            )
            self._pad.right_joystick_float(
                x_value_float=s["right_x"],
                y_value_float=s["right_y"],
            )
            self._pad.left_trigger_float(value_float=s["trigger_l"])
            self._pad.right_trigger_float(value_float=s["trigger_r"])
            self._pad.update()
        except Exception as exc:
            logger.error("GamepadDevice flush error: %s", exc)

    def reset(self) -> None:
        """Zero all axes (call on plugin disable)."""
        if self._pad is None:
            return
        with self._lock:
            for k in self._state:
                self._state[k] = 0.0
            self._flush()

    def close(self) -> None:
        """Release the virtual device."""
        self.reset()
        # vgamepad has no explicit close; garbage-collection handles it.
        self._pad = None


# Module-level singleton — created lazily on first use
_DEVICE: Optional[_GamepadDevice] = None
_DEVICE_LOCK = threading.Lock()


def _get_device() -> _GamepadDevice:
    global _DEVICE
    if _DEVICE is None:
        with _DEVICE_LOCK:
            if _DEVICE is None:
                _DEVICE = _GamepadDevice()
    return _DEVICE


def shutdown_device() -> None:
    """Call when the plugin is disabled to release the virtual pad."""
    global _DEVICE
    if _DEVICE is not None:
        _DEVICE.close()
        _DEVICE = None


# ── GamepadAxisOutput ─────────────────────────────────────────────────────────

class GamepadAxisOutput:
    """
    AnalogOutput backend that writes slider values to a virtual Xbox 360 axis.

    config keys
    -----------
    axis        str    target axis name (see module docstring)
    deadzone    float  center deadzone fraction for joystick axes (default 0.05)
    invert      bool   flip direction (default False)
    """

    # Register with the analog_output factory
    output_type = "gamepad_axis"

    def apply(self, raw: float, normalised: float, config: dict) -> None:
        """
        Receive a slider update and forward it to the virtual gamepad.

        ``normalised`` is already in [0, 1] — this method converts it to the
        correct range for the chosen axis type.
        """
        axis = config.get("axis", "")
        if axis not in _ALL_AXES:
            logger.warning("gamepad_axis output: invalid axis %r — skipping", axis)
            return

        invert   = bool(config.get("invert", False))
        deadzone = float(config.get("deadzone", 0.05))

        n = normalised          # 0.0 … 1.0

        if invert:
            n = 1.0 - n

        if axis in _JOYSTICK_AXES:
            # Map [0, 1] → [-1, +1]
            value = n * 2.0 - 1.0
            # Apply symmetric deadzone around centre
            if abs(value) < deadzone:
                value = 0.0
        else:
            # Trigger: keep as [0, 1]
            value = n

        _get_device().set_axis(axis, value)

    def cleanup(self) -> None:
        """Zero the axis when this output is removed."""
        # We can't zero a specific axis without knowing which one — the config
        # dict isn't available here.  shutdown_device() handles full reset.
        pass
