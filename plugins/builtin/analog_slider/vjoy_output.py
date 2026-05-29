"""
vjoy_output.py  —  Virtual DirectInput joystick axis output for the Analog Slider plugin.

Uses the ``pyvjoy`` package (which wraps the vJoy driver) to expose a virtual
DirectInput joystick that flight simulators (DCS, MSFS, X-Plane, IL-2, etc.)
see as a real HOTAS/throttle device.

Why vJoy instead of (or alongside) ViGEm
-----------------------------------------
ViGEm creates an Xbox 360 / DualShock 4 controller.  Those are great for games
that use XInput, but flight simulators use DirectInput and expect proper named
axes: X, Y, Z, Rx, Ry, Rz, Slider0, Slider1.  Additionally, the Xbox trigger
axes share a single Z channel in DirectInput (left trigger + positive, right
trigger + negative), making independent throttle/mixture/prop binding impossible.

vJoy exposes up to 8 fully independent axes per device (up to 16 devices total)
in the exact format flight sims expect.  A single vJoy device with Slider0 set
as "throttle" and Slider1 as "mixture" is indistinguishable from a real HOTAS.

Axis identifiers
-----------------
  X        Primary horizontal          (HID usage 0x30)
  Y        Primary vertical            (HID usage 0x31)
  Z        Primary depth / throttle    (HID usage 0x32)
  Rx       Secondary horizontal roll   (HID usage 0x33)
  Ry       Secondary vertical pitch    (HID usage 0x34)
  Rz       Secondary yaw / rudder      (HID usage 0x35)
  Slider0  Extra axis — ideal throttle (HID usage 0x36)
  Slider1  Extra axis — mixture/prop   (HID usage 0x37)

Config keys  (per output entry in slider_config["outputs"])
-----------------------------------------------------------
  device   int   vJoy device ID, 1-based (default 1)
  axis     str   axis name from the list above (default "Slider0")
  invert   bool  flip the direction (default False)
  range_lo float low end of output range — 0-1 fraction OR 0-100 percent (default 0.0)
  range_hi float high end of output range — 0-1 fraction OR 0-100 percent (default 1.0)

range_lo / range_hi allow you to map the physical slider travel to a partial
axis range, e.g. range_lo=0.1, range_hi=0.9 to add end-stops.
Values > 1 are treated as percentages and automatically divided by 100,
so range_hi=100 (stored by the editor) is equivalent to range_hi=1.0.

Prerequisites
-------------
1. Install vJoy driver:  https://github.com/jshafer817/vJoy/releases
   (or the maintained fork:  https://github.com/njz3/vJoy/releases)
2. Open "Configure vJoy" and enable the axes you need on each device.
3. pip install pyvjoy

Graceful degradation
--------------------
If pyvjoy is not importable (Linux / no vJoy driver) every call is a no-op
and a one-time warning is logged.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger("plugin.analog_slider.vjoy")

# ── vJoy axis name → HID usage ID ─────────────────────────────────────────────
AXIS_IDS: Dict[str, int] = {
    "X":       0x30,
    "Y":       0x31,
    "Z":       0x32,
    "Rx":      0x33,
    "Ry":      0x34,
    "Rz":      0x35,
    "Slider0": 0x36,
    "Slider1": 0x37,
}

# vJoy axis range is always 0 – 32767
_VJOY_MAX: int = 32767

# ── lazy import ───────────────────────────────────────────────────────────────
_PYVJOY_AVAILABLE = False
_pyvjoy = None
try:
    import pyvjoy as _pyvjoy          # type: ignore
    _PYVJOY_AVAILABLE = True
except ImportError:
    logger.warning(
        "pyvjoy not installed — vJoy axis output disabled. "
        "Install with: pip install pyvjoy  "
        "(also requires the vJoy driver: https://github.com/jshafer817/vJoy/releases)"
    )
except Exception as exc:
    logger.warning("pyvjoy import error: %s — vJoy axis output disabled", exc)


# ── Per-device singleton ───────────────────────────────────────────────────────

class _VJoyDevice:
    """
    Wraps one acquired vJoy device and keeps its axis state.
    Thread-safe.

    Auto-reacquire
    --------------
    If the vJoy driver resets the device (e.g. the vJoy Monitor app was used,
    or another process grabbed then released the device) the underlying
    pyvjoy.VJoyDevice handle becomes stale and set_axis raises an exception
    with an empty message.  On any such failure we drop the handle and
    immediately try to re-acquire, then retry the failed call once.
    """

    def __init__(self, device_id: int) -> None:
        self.device_id = device_id
        self._lock  = threading.Lock()
        self._dev   = None     # pyvjoy.VJoyDevice or None
        self._state: Dict[int, int] = {}   # HID usage → 0..32767

        if not _PYVJOY_AVAILABLE or _pyvjoy is None:
            return
        try:
            self._dev = _pyvjoy.VJoyDevice(device_id)
            logger.info("Acquired vJoy device %d", device_id)
        except Exception as exc:
            self._dev = None
            logger.error(
                "Could not acquire vJoy device %d: %s  "
                "(Is vJoy installed and device %d configured in 'Configure vJoy'?)",
                device_id, exc, device_id,
            )

    @property
    def available(self) -> bool:
        return self._dev is not None

    # ------------------------------------------------------------------
    def _reacquire(self) -> None:
        """
        Drop the stale handle and attempt a fresh acquisition.
        Must be called while self._lock is already held.
        """
        if not _PYVJOY_AVAILABLE or _pyvjoy is None:
            return
        logger.warning("vJoy device %d: attempting re-acquire after failure", self.device_id)
        self._dev = None
        try:
            self._dev = _pyvjoy.VJoyDevice(self.device_id)
            logger.info("vJoy device %d re-acquired successfully", self.device_id)
        except Exception as exc:
            self._dev = None
            logger.error(
                "vJoy device %d re-acquire failed: %s  "
                "(Check vJoy Monitor — is the device still configured?)",
                self.device_id, exc,
            )

    # ------------------------------------------------------------------
    def set_axis(self, hid_usage: int, normalised: float) -> None:
        """
        Set one axis.

        Parameters
        ----------
        hid_usage   : HID usage ID (use AXIS_IDS dict)
        normalised  : 0.0 … 1.0
        """
        if self._dev is None:
            return
        value = int(round(normalised * _VJOY_MAX))
        value = max(0, min(_VJOY_MAX, value))
        with self._lock:
            self._state[hid_usage] = value
            try:
                self._dev.set_axis(hid_usage, value)
            except Exception as exc:
                # Handle goes stale when vJoy Monitor resets the device or
                # another process temporarily acquires it.  Empty exception
                # message is the tell-tale sign.
                logger.warning(
                    "vJoy device %d set_axis(0x%02x, %d) failed: %s — attempting re-acquire",
                    self.device_id, hid_usage, value, exc,
                )
                self._reacquire()
                if self._dev is not None:
                    try:
                        self._dev.set_axis(hid_usage, value)
                        logger.info(
                            "vJoy device %d recovered — set_axis(0x%02x, %d) succeeded after re-acquire",
                            self.device_id, hid_usage, value,
                        )
                    except Exception as exc2:
                        logger.error(
                            "vJoy device %d set_axis(0x%02x, %d) still failed after re-acquire: %s",
                            self.device_id, hid_usage, value, exc2,
                        )

    def reset(self) -> None:
        """Zero all axes on this device."""
        if self._dev is None:
            return
        with self._lock:
            for usage in list(self._state):
                try:
                    self._dev.set_axis(usage, 0)
                except Exception:
                    pass
            self._state.clear()

    def close(self) -> None:
        self.reset()
        self._dev = None


# Module-level device registry: device_id (1-based) → _VJoyDevice
_DEVICES: Dict[int, _VJoyDevice] = {}
_DEVICES_LOCK = threading.Lock()


def _get_device(device_id: int) -> _VJoyDevice:
    if device_id not in _DEVICES:
        with _DEVICES_LOCK:
            if device_id not in _DEVICES:
                _DEVICES[device_id] = _VJoyDevice(device_id)
    return _DEVICES[device_id]


def shutdown_vjoy() -> None:
    """Release all vJoy devices.  Call on plugin disable."""
    global _DEVICES
    with _DEVICES_LOCK:
        for dev in _DEVICES.values():
            try:
                dev.close()
            except Exception:
                pass
        _DEVICES.clear()
    logger.info("All vJoy devices released")


# ── VJoyAxisOutput ─────────────────────────────────────────────────────────────

class VJoyAxisOutput:
    """
    AnalogOutput backend that writes slider values to a vJoy device axis.

    config keys
    -----------
    device    int   vJoy device ID, 1-16 (default 1)
    axis      str   axis name: X Y Z Rx Ry Rz Slider0 Slider1 (default Slider0)
    invert    bool  flip direction (default False)
    range_lo  float low-end of output range (default 0.0)
    range_hi  float high-end of output range (default 1.0)

    range_lo/range_hi may be stored as 0-100 percentages (e.g. range_hi=100).
    Any value > 1 is automatically divided by 100 before use.
    """

    output_type = "vjoy_axis"

    def apply(self, raw: float, normalised: float, config: dict) -> None:
        device_id = int(config.get("device", 1))
        axis_name = config.get("axis", "Slider0")
        invert    = bool(config.get("invert", False))
        range_lo  = float(config.get("range_lo", 0.0))
        range_hi  = float(config.get("range_hi", 1.0))

        # ── FIX: auto-normalise range bounds stored as 0-100 percentages ──
        # The editor saves range_hi=100 to mean "full range", but the
        # mapping logic expects 0-1 fractions.  Dividing by 100 converts
        # both styles to the same internal representation.
        if range_hi > 1.0 or range_lo > 1.0:
            range_lo /= 100.0
            range_hi /= 100.0

        hid_usage = AXIS_IDS.get(axis_name)
        if hid_usage is None:
            logger.warning("vjoy_axis: unknown axis %r — must be one of %s",
                           axis_name, list(AXIS_IDS))
            return

        n = normalised   # 0.0 … 1.0
        if invert:
            n = 1.0 - n
        span = range_hi - range_lo
        n = range_lo + n * span
        n = max(0.0, min(1.0, n))
        vjoy_val = int(round(n * _VJOY_MAX))

        logger.debug(
            "vjoy_axis → device=%d axis=%s hid=0x%02x normalised=%.3f vjoy=%d",
            device_id, axis_name, hid_usage, n, vjoy_val
        )

        dev = _get_device(device_id)
        if not dev.available:
            logger.warning(
                "vjoy_axis: vJoy device %d not available. "
                "Is the vJoy driver installed and device %d configured in 'Configure vJoy'?",
                device_id, device_id
            )
            return

        dev.set_axis(hid_usage, n)

    def cleanup(self) -> None:
        pass   # individual axis reset not possible without config; shutdown_vjoy() handles it