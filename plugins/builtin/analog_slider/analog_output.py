"""
analog_output.py  —  output backends for the Analog Slider plugin.

Each output is a class with a single method:
    apply(raw: float, normalised: float, config: dict) -> None

  raw        = current slider value in [min_value, max_value]
  normalised = value mapped to [0.0, 1.0]
  config     = dict of per-output options from slider_config["outputs"][i]

Available outputs
-----------------
VariableOutput           — write raw/normalised to a VariableManager variable
KeyboardThresholdOutput  — press/hold/release keys when crossing value zones
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("plugin.analog_slider.output")


class AnalogOutput(ABC):
    """Base class for all slider output backends."""

    @abstractmethod
    def apply(self, raw: float, normalised: float, config: dict) -> None:
        """
        React to a new slider value.

        Parameters
        ----------
        raw        : actual value in the slider's [min, max] range
        normalised : value mapped to [0.0, 1.0]
        config     : this output's configuration dict
        """

    def cleanup(self) -> None:
        """Called when the slider is removed. Release any held resources."""


# ── VariableOutput ────────────────────────────────────────────────────

class VariableOutput(AnalogOutput):
    """
    Write the slider value to a Macro Deck variable.

    config keys:
      variable_name   str   name of the variable (default "slider_value")
      variable_type   str   Float | Integer | String | Bool (default Float)
      use_normalised  bool  write normalised [0,1] instead of raw (default False)
    """

    def apply(self, raw: float, normalised: float, config: dict) -> None:
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType

        name     = config.get("variable_name", "slider_value")
        use_norm = config.get("use_normalised", False)
        vtype_s  = config.get("variable_type", "Float")

        try:
            vtype = VariableType(vtype_s)
        except ValueError:
            vtype = VariableType.FLOAT

        source = normalised if use_norm else raw

        if vtype == VariableType.INTEGER:
            value = round(source)
        elif vtype == VariableType.FLOAT:
            value = float(source)
        elif vtype == VariableType.BOOL:
            value = source >= 0.5
        else:
            value = str(source)

        VariableManager.set_value(name, value, vtype,
                                  plugin_id="builtin.analog_slider", save=False)


# ── KeyboardThresholdOutput ───────────────────────────────────────────

class KeyboardThresholdOutput(AnalogOutput):
    """
    Fire key combos when the slider enters a value zone.

    config keys:
      thresholds  list of zone dicts:
        { "min": float, "max": float,
          "keys": [str, ...],          # 1–5 key names
          "mode": "crossing" | "zone"  # see below
        }

    Modes
    -----
    crossing  (default)
      Press the key combo once when the slider *enters* the zone.
      Nothing happens while staying inside the zone.

    zone
      Hold the keys down while inside the zone,
      release them when leaving.
    """

    def __init__(self):
        self._active_zone: Optional[int] = None  # index of currently active zone

    def apply(self, raw: float, normalised: float, config: dict) -> None:
        from macro_deck_python.plugins.builtin.keyboard_macro import injector

        thresholds: List[dict] = config.get("thresholds", [])
        if not thresholds:
            return

        # Find which zone raw falls into (first match wins)
        new_zone: Optional[int] = None
        for i, z in enumerate(thresholds):
            if z.get("min", 0) <= raw <= z.get("max", 100):
                new_zone = i
                break

        if new_zone == self._active_zone:
            return   # no zone change — nothing to do

        prev_zone = self._active_zone
        self._active_zone = new_zone

        # Release previous zone's held keys (zone mode)
        if prev_zone is not None:
            z = thresholds[prev_zone]
            if z.get("mode", "crossing") == "zone":
                keys = z.get("keys", [])
                for k in reversed(keys):
                    try:
                        injector.up(k)
                    except Exception as exc:
                        logger.debug("up %s: %s", k, exc)

        # Activate new zone
        if new_zone is not None:
            z = thresholds[new_zone]
            keys = z.get("keys", [])
            mode = z.get("mode", "crossing")
            if mode == "crossing":
                if len(keys) == 1:
                    try:
                        injector.press(keys[0])
                    except Exception as exc:
                        logger.debug("press %s: %s", keys[0], exc)
                elif len(keys) > 1:
                    try:
                        injector.combo(keys)
                    except Exception as exc:
                        logger.debug("combo %s: %s", keys, exc)
            else:  # zone mode — hold
                for k in keys:
                    try:
                        injector.down(k)
                    except Exception as exc:
                        logger.debug("down %s: %s", k, exc)

    def cleanup(self) -> None:
        """Release any held keys on cleanup."""
        # We don't have the config here, so just reset state
        self._active_zone = None


# ── Factory ───────────────────────────────────────────────────────────

_OUTPUT_REGISTRY: Dict[str, type] = {
    "variable":  VariableOutput,
    "threshold": KeyboardThresholdOutput,
}


def make_output(output_type: str) -> Optional[AnalogOutput]:
    """Instantiate an AnalogOutput by type name."""
    cls = _OUTPUT_REGISTRY.get(output_type)
    if cls is None:
        logger.warning("Unknown output type: %r", output_type)
        return None
    return cls()
